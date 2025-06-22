import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
import boto3
import stripe
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
eventbridge = boto3.client('events')

# Environment variables
TABLE_NAME = os.environ.get('MRR_TABLE_NAME', 'BillingMetrics')
STRIPE_SECRET_NAME = os.environ.get('STRIPE_SECRET_NAME', '/contentcraft/stripe/api_key')


def get_stripe_api_key() -> Optional[str]:
    """Retrieve Stripe API key from Secrets Manager"""
    try:
        response = secrets_manager.get_secret_value(SecretId=STRIPE_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        return secret.get('api_key')
    except ClientError as e:
        logger.error(f"Could not retrieve Stripe API key: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error retrieving Stripe API key: {str(e)}")
        return None


def calculate_mrr_from_stripe() -> Decimal:
    """Calculate MRR from Stripe balance transactions over the last 30 days"""
    try:
        # Get Stripe API key
        api_key = get_stripe_api_key()
        if not api_key:
            logger.error("Stripe API key not found")
            return Decimal('0')
        
        stripe.api_key = api_key
        
        # Calculate date range (last 30 days)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        # Convert to Unix timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        logger.info(f"Fetching Stripe transactions from {start_date} to {end_date}")
        
        # Fetch balance transactions
        total_revenue = Decimal('0')
        has_more = True
        starting_after = None
        
        while has_more:
            params = {
                'limit': 100,
                'created': {
                    'gte': start_timestamp,
                    'lte': end_timestamp
                },
                'type': 'charge'  # Only successful charges
            }
            
            if starting_after:
                params['starting_after'] = starting_after
            
            # Fetch transactions
            transactions = stripe.BalanceTransaction.list(**params)
            
            for transaction in transactions.data:
                # Only count successful charges (not refunds)
                if transaction.type == 'charge' and transaction.net > 0:
                    # Convert from cents to dollars
                    amount = Decimal(str(transaction.net)) / 100
                    total_revenue += amount
                    
                    # Handle refunds separately
                elif transaction.type == 'refund':
                    # Refunds are negative amounts
                    amount = Decimal(str(transaction.net)) / 100
                    total_revenue += amount  # This will subtract since it's negative
            
            # Check if there are more transactions
            has_more = transactions.has_more
            if has_more and transactions.data:
                starting_after = transactions.data[-1].id
        
        logger.info(f"Total revenue from last 30 days: ${total_revenue}")
        
        # MRR is the 30-day revenue (already calculated)
        # This assumes consistent revenue patterns
        mrr = total_revenue
        
        return mrr
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error: {str(e)}")
        return Decimal('0')
    except Exception as e:
        logger.error(f"Error calculating MRR: {str(e)}")
        return Decimal('0')


def save_mrr_to_dynamodb(mrr_value: Decimal) -> bool:
    """Save MRR value to DynamoDB"""
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Save latest MRR
        table.put_item(
            Item={
                'PK': 'mrr',
                'SK': 'latest',
                'mrrUSD': float(mrr_value),
                'ts': timestamp,
                'ttl': int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())
            }
        )
        
        # Also save historical record
        table.put_item(
            Item={
                'PK': 'mrr-history',
                'SK': timestamp,
                'mrrUSD': float(mrr_value),
                'ttl': int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp())
            }
        )
        
        logger.info(f"MRR saved to DynamoDB: ${mrr_value}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving MRR to DynamoDB: {str(e)}")
        return False


def publish_event(mrr_value: Decimal) -> bool:
    """Publish MRR reported event to EventBridge"""
    try:
        event_detail = {
            'mrrUSD': float(mrr_value),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'mrr-reporter'
        }
        
        response = eventbridge.put_events(
            Entries=[
                {
                    'Source': 'billing.mrr',
                    'DetailType': 'MRR Reported',
                    'Detail': json.dumps(event_detail)
                }
            ]
        )
        
        if response['FailedEntryCount'] == 0:
            logger.info("MRR event published to EventBridge")
            return True
        else:
            logger.error(f"Failed to publish event: {response}")
            return False
            
    except Exception as e:
        logger.error(f"Error publishing event: {str(e)}")
        return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for MRR Reporter
    Runs daily to calculate and store MRR from Stripe
    """
    logger.info("Starting MRR Reporter")
    
    try:
        # Calculate MRR from Stripe
        mrr_value = calculate_mrr_from_stripe()
        
        if mrr_value <= 0:
            logger.warning("MRR calculation returned zero or negative value")
            # Continue anyway to record the value
        
        # Save to DynamoDB
        saved = save_mrr_to_dynamodb(mrr_value)
        
        # Publish event (optional)
        event_published = publish_event(mrr_value)
        
        result = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'mrrUSD': float(mrr_value),
            'saved': saved,
            'eventPublished': event_published
        }
        
        logger.info(f"MRR Reporter complete: {json.dumps(result)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }