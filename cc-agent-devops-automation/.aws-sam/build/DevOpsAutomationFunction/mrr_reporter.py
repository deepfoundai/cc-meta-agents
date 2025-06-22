import json
import os
import boto3
import stripe
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from decimal import Decimal

# Initialize AWS clients
secrets_manager = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')
events_client = boto3.client('events')

# Environment variables
BILLING_METRICS_TABLE = os.environ.get('BILLING_METRICS_TABLE', 'BillingMetrics-dev')
STRIPE_SECRET_PATH = os.environ.get('STRIPE_SECRET_PATH', '/contentcraft/stripe/reporting_api_key')

def get_stripe_api_key():
    """Get Stripe API key from Secrets Manager"""
    try:
        response = secrets_manager.get_secret_value(SecretId=STRIPE_SECRET_PATH)
        return response['SecretString']
    except Exception as e:
        print(f"Error retrieving Stripe API key: {str(e)}")
        raise

def calculate_mrr_from_stripe(days_back: int = 30) -> Dict[str, Any]:
    """
    Calculate MRR from Stripe transactions over the specified period
    """
    try:
        # Get Stripe API key
        api_key = get_stripe_api_key()
        stripe.api_key = api_key
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        # Convert to Unix timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        print(f"Calculating MRR from {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Fetch balance transactions (charges and refunds)
        transactions = []
        starting_after = None
        
        while True:
            params = {
                'type': 'charge',
                'created': {
                    'gte': start_timestamp,
                    'lte': end_timestamp
                },
                'limit': 100
            }
            
            if starting_after:
                params['starting_after'] = starting_after
            
            try:
                response = stripe.BalanceTransaction.list(**params)
                transactions.extend(response.data)
                
                if not response.has_more:
                    break
                    
                starting_after = response.data[-1].id
                
            except stripe.error.RateLimitError:
                print("Rate limit hit, waiting before retry...")
                import time
                time.sleep(1)
                continue
            except Exception as e:
                print(f"Error fetching transactions: {str(e)}")
                break
        
        # Also fetch refunds
        refunds = []
        starting_after = None
        
        while True:
            params = {
                'created': {
                    'gte': start_timestamp,
                    'lte': end_timestamp
                },
                'limit': 100
            }
            
            if starting_after:
                params['starting_after'] = starting_after
            
            try:
                response = stripe.Refund.list(**params)
                refunds.extend(response.data)
                
                if not response.has_more:
                    break
                    
                starting_after = response.data[-1].id
                
            except stripe.error.RateLimitError:
                print("Rate limit hit, waiting before retry...")
                import time
                time.sleep(1)
                continue
            except Exception as e:
                print(f"Error fetching refunds: {str(e)}")
                break
        
        # Calculate totals
        total_charges = sum(tx.amount for tx in transactions if tx.type == 'charge')
        total_refunds = sum(refund.amount for refund in refunds)
        
        # Convert from cents to dollars
        charges_usd = total_charges / 100
        refunds_usd = total_refunds / 100
        net_revenue = charges_usd - refunds_usd
        
        # Calculate MRR (Monthly Recurring Revenue)
        # For simplicity, we'll use the net revenue over the period as MRR
        mrr_usd = net_revenue
        
        print(f"Calculated MRR: ${mrr_usd:.2f} (Charges: ${charges_usd:.2f}, Refunds: ${refunds_usd:.2f})")
        
        return {
            'mrrUSD': mrr_usd,
            'charges_usd': charges_usd,
            'refunds_usd': refunds_usd,
            'charge_count': len(transactions),
            'refund_count': len(refunds),
            'total_transactions': len(transactions) + len(refunds),
            'period_days': days_back,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }
        
    except Exception as e:
        print(f"Error calculating MRR: {str(e)}")
        raise

def store_mrr_metrics(mrr_data: Dict[str, Any]) -> None:
    """Store MRR metrics in DynamoDB"""
    try:
        table = dynamodb.Table(BILLING_METRICS_TABLE)
        
        # Prepare item for DynamoDB
        item = {
            'PK': 'mrr',
            'SK': 'latest',
            'mrrUSD': Decimal(str(mrr_data['mrrUSD'])),
            'charges_usd': Decimal(str(mrr_data['charges_usd'])),
            'refunds_usd': Decimal(str(mrr_data['refunds_usd'])),
            'charge_count': mrr_data['charge_count'],
            'refund_count': mrr_data['refund_count'],
            'total_transactions': mrr_data['total_transactions'],
            'period_days': mrr_data['period_days'],
            'ts': datetime.now(timezone.utc).isoformat(),
            'start_date': mrr_data['start_date'],
            'end_date': mrr_data['end_date']
        }
        
        table.put_item(Item=item)
        print(f"Stored MRR metrics in DynamoDB: {BILLING_METRICS_TABLE}")
        
    except Exception as e:
        print(f"Error storing MRR metrics: {str(e)}")
        raise

def publish_mrr_event(mrr_data: Dict[str, Any]) -> None:
    """Publish MRR calculation event to EventBridge"""
    try:
        event_detail = {
            'source': 'stripe-mrr-reporter',
            'action': 'mrr_calculated',
            'mrrUSD': mrr_data['mrrUSD'],
            'period_days': mrr_data['period_days'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        events_client.put_events(
            Entries=[
                {
                    'Source': 'contentcraft.billing',
                    'DetailType': 'MRR Calculation Complete',
                    'Detail': json.dumps(event_detail)
                }
            ]
        )
        
        print(f"Published MRR event: ${mrr_data['mrrUSD']:.2f}")
        
    except Exception as e:
        print(f"Error publishing MRR event: {str(e)}")
        # Don't raise - this is not critical

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Stripe MRR reporting
    Calculates and stores monthly recurring revenue metrics
    """
    try:
        print("Starting MRR calculation...")
        
        # Calculate MRR from Stripe
        mrr_data = calculate_mrr_from_stripe(days_back=30)
        
        # Store in DynamoDB
        store_mrr_metrics(mrr_data)
        
        # Publish event
        publish_mrr_event(mrr_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'mrrUSD': mrr_data['mrrUSD'],
                'charge_count': mrr_data['charge_count'],
                'refund_count': mrr_data['refund_count'],
                'period_days': mrr_data['period_days'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }
        
    except Exception as e:
        error_msg = f"MRR calculation failed: {str(e)}"
        print(error_msg)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': error_msg,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }