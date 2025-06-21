import os
import json
import time
import boto3
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
import logging
import openai
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')
ssm = boto3.client('ssm')

# Table names from environment
JOBS_TABLE = os.environ.get('JOBS_TABLE', 'Jobs')
CREDITS_TABLE = os.environ.get('CREDITS_TABLE', 'Credits')
LEDGER_TABLE = os.environ.get('LEDGER_TABLE', 'Ledger')

# OpenAI setup
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4.1')
client = None

if OPENAI_API_KEY:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler that routes events to appropriate processors."""
    try:
        # Log the incoming event
        logger.info(json.dumps({
            'level': 'info',
            'msg': 'Processing event',
            'eventType': event.get('source', 'unknown'),
            'detail-type': event.get('detail-type', 'unknown')
        }))
        
        # Route based on event type
        if event.get('source') == 'aws.events' and event.get('detail-type'):
            # EventBridge events
            detail_type = event['detail-type']
            detail = event.get('detail', {})
            
            if detail_type == 'video.rendered':
                return handle_video_rendered(detail)
            elif detail_type == 'video.failed':
                return handle_video_failed(detail)
        elif event.get('source') == 'aws.events' and 'Scheduled Event' in event.get('detail-type', ''):
            # Scheduled timer scan
            return handle_timer_scan()
        else:
            logger.warning(f"Unhandled event type: {event.get('source')}")
            
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Event processed'})
        }
        
    except Exception as e:
        logger.error(json.dumps({
            'level': 'error',
            'msg': 'Lambda handler error',
            'error': str(e),
            'event': event
        }))
        # Let it bubble up to DLQ
        raise


def handle_video_rendered(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Process video.rendered events and debit user credits."""
    job_id = detail.get('jobId')
    user_id = detail.get('userId')
    seconds = detail.get('seconds', 0)
    model = detail.get('model', 'default')
    
    if not all([job_id, user_id, seconds]):
        logger.error(f"Missing required fields in video.rendered event: {detail}")
        return {'statusCode': 400, 'body': 'Missing required fields'}
    
    try:
        # Check if already processed (idempotent)
        ledger_table = dynamodb.Table(LEDGER_TABLE)
        existing = ledger_table.query(
            IndexName='JobIdIndex',  # Assuming we have a GSI on jobId
            KeyConditionExpression=Key('jobId').eq(job_id),
            FilterExpression=Attr('type').eq('debit')
        )
        
        if existing['Count'] > 0:
            logger.info(f"Job {job_id} already debited, skipping")
            return {'statusCode': 200, 'body': 'Already processed'}
        
        # Get pricing from SSM Parameter Store
        price_per_second = get_model_price(model)
        cost = Decimal(str(seconds)) * Decimal(str(price_per_second))
        
        # Create ledger entry
        timestamp = datetime.utcnow().isoformat()
        ledger_id = f"{user_id}#{timestamp}#{job_id}"
        
        ledger_item = {
            'ledgerId': ledger_id,
            'userId': user_id,
            'timestamp': timestamp,
            'type': 'debit',
            'amount': cost,
            'reference': job_id,
            'jobId': job_id,  # For GSI
            'description': f'Video generation - {seconds}s @ {model}'
        }
        
        # Check for anomalies before processing
        if is_anomaly(cost, seconds, detail):
            anomaly_msg = invoke_llm(
                f"Explain this video generation anomaly in ≤2 sentences: "
                f"cost=${cost}, seconds={seconds}, model={model}, "
                f"jobId={job_id}"
            )
            ledger_item['anomaly'] = anomaly_msg
            logger.warning(json.dumps({
                'level': 'warning',
                'msg': 'Anomaly detected',
                'jobId': job_id,
                'userId': user_id,
                'cost': float(cost),
                'anomaly': anomaly_msg
            }))
        
        # Write to ledger
        ledger_table.put_item(Item=ledger_item)
        
        # Update user credits (atomic decrement)
        credits_table = dynamodb.Table(CREDITS_TABLE)
        response = credits_table.update_item(
            Key={'userId': user_id},
            UpdateExpression='SET remaining = remaining - :cost',
            ExpressionAttributeValues={':cost': cost},
            ReturnValues='ALL_NEW'
        )
        
        # Update job reconciliation status
        jobs_table = dynamodb.Table(JOBS_TABLE)
        jobs_table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET reconciled = :true',
            ExpressionAttributeValues={':true': True}
        )
        
        # Emit metric
        emit_metric('Adjustments', 1, 'Count')
        
        logger.info(json.dumps({
            'level': 'info',
            'msg': 'Credit debited',
            'jobId': job_id,
            'userId': user_id,
            'cost': float(cost),
            'remaining': float(response['Attributes']['remaining'])
        }))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Credit debited',
                'cost': float(cost),
                'remaining': float(response['Attributes']['remaining'])
            })
        }
        
    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error processing video.rendered: {e}")
        raise


def handle_video_failed(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Process video.failed events and refund user credits."""
    job_id = detail.get('jobId')
    user_id = detail.get('userId')
    
    if not all([job_id, user_id]):
        logger.error(f"Missing required fields in video.failed event: {detail}")
        return {'statusCode': 400, 'body': 'Missing required fields'}
    
    try:
        # Find the original debit
        ledger_table = dynamodb.Table(LEDGER_TABLE)
        debits = ledger_table.query(
            IndexName='JobIdIndex',
            KeyConditionExpression=Key('jobId').eq(job_id),
            FilterExpression=Attr('type').eq('debit')
        )
        
        if debits['Count'] == 0:
            logger.info(f"No debit found for failed job {job_id}")
            return {'statusCode': 200, 'body': 'No debit to refund'}
        
        # Check if already refunded
        refunds = ledger_table.query(
            IndexName='JobIdIndex',
            KeyConditionExpression=Key('jobId').eq(job_id),
            FilterExpression=Attr('type').eq('credit')
        )
        
        if refunds['Count'] > 0:
            logger.info(f"Job {job_id} already refunded")
            return {'statusCode': 200, 'body': 'Already refunded'}
        
        # Process refund
        original_debit = debits['Items'][0]
        refund_amount = original_debit['amount']
        
        # Create refund ledger entry
        timestamp = datetime.utcnow().isoformat()
        ledger_id = f"{user_id}#{timestamp}#{job_id}#refund"
        
        refund_item = {
            'ledgerId': ledger_id,
            'userId': user_id,
            'timestamp': timestamp,
            'type': 'credit',
            'amount': refund_amount,
            'reference': job_id,
            'jobId': job_id,
            'description': f'Refund for failed job {job_id}'
        }
        
        ledger_table.put_item(Item=refund_item)
        
        # Update user credits (atomic increment)
        credits_table = dynamodb.Table(CREDITS_TABLE)
        response = credits_table.update_item(
            Key={'userId': user_id},
            UpdateExpression='SET remaining = remaining + :amount',
            ExpressionAttributeValues={':amount': refund_amount},
            ReturnValues='ALL_NEW'
        )
        
        # Update job reconciliation status
        jobs_table = dynamodb.Table(JOBS_TABLE)
        jobs_table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET reconciled = :true',
            ExpressionAttributeValues={':true': True}
        )
        
        # Emit metric
        emit_metric('Adjustments', 1, 'Count')
        
        logger.info(json.dumps({
            'level': 'info',
            'msg': 'Credit refunded',
            'jobId': job_id,
            'userId': user_id,
            'refund': float(refund_amount),
            'remaining': float(response['Attributes']['remaining'])
        }))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Credit refunded',
                'refund': float(refund_amount),
                'remaining': float(response['Attributes']['remaining'])
            })
        }
        
    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error processing video.failed: {e}")
        raise


def handle_timer_scan() -> Dict[str, Any]:
    """Scan for unreconciled completed/failed jobs and process them."""
    try:
        jobs_table = dynamodb.Table(JOBS_TABLE)
        
        # Scan for unreconciled jobs
        response = jobs_table.scan(
            FilterExpression=(
                Attr('status').is_in(['completed', 'failed']) & 
                (Attr('reconciled').eq(False) | Attr('reconciled').not_exists())
            )
        )
        
        processed_count = 0
        error_count = 0
        
        for job in response['Items']:
            try:
                if job['status'] == 'completed':
                    # Simulate video.rendered event
                    result = handle_video_rendered({
                        'jobId': job['jobId'],
                        'userId': job['userId'],
                        'seconds': job.get('seconds', 0),
                        'model': job.get('model', 'default')
                    })
                elif job['status'] == 'failed':
                    # Simulate video.failed event
                    result = handle_video_failed({
                        'jobId': job['jobId'],
                        'userId': job['userId']
                    })
                
                if result['statusCode'] == 200:
                    processed_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing job {job['jobId']}: {e}")
                error_count += 1
        
        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = jobs_table.scan(
                FilterExpression=(
                    Attr('status').is_in(['completed', 'failed']) & 
                    (Attr('reconciled').eq(False) | Attr('reconciled').not_exists())
                ),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            
            for job in response['Items']:
                try:
                    if job['status'] == 'completed':
                        result = handle_video_rendered({
                            'jobId': job['jobId'],
                            'userId': job['userId'],
                            'seconds': job.get('seconds', 0),
                            'model': job.get('model', 'default')
                        })
                    elif job['status'] == 'failed':
                        result = handle_video_failed({
                            'jobId': job['jobId'],
                            'userId': job['userId']
                        })
                    
                    if result['statusCode'] == 200:
                        processed_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing job {job['jobId']}: {e}")
                    error_count += 1
        
        logger.info(json.dumps({
            'level': 'info',
            'msg': 'Timer scan completed',
            'processed': processed_count,
            'errors': error_count
        }))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Timer scan completed',
                'processed': processed_count,
                'errors': error_count
            })
        }
        
    except Exception as e:
        logger.error(f"Error in timer scan: {e}")
        raise


def get_model_price(model: str) -> float:
    """Get the price per second for a given model from SSM Parameter Store."""
    try:
        parameter_name = f"/fertilia/pricing/{model}"
        response = ssm.get_parameter(Name=parameter_name)
        return float(response['Parameter']['Value'])
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            # Default pricing if model not found
            logger.warning(f"Price not found for model {model}, using default")
            return 0.10  # Default $0.10 per second
        raise


def is_anomaly(cost: Decimal, seconds: int, detail: Dict[str, Any]) -> bool:
    """Check if a job represents an anomaly based on cost and other factors."""
    # Check if cost is unusually high (> $50)
    if cost > 50:
        return True
    
    # Check if seconds is unusually high (> 300 seconds / 5 minutes)
    if seconds > 300:
        return True
    
    # Check if result_url is missing
    if not detail.get('result_url'):
        return True
    
    # TODO: Implement median-based anomaly detection
    # For now, using fixed thresholds
    
    return False


def invoke_llm(prompt: str) -> Optional[str]:
    """Invoke LLM for anomaly explanation or other assistance."""
    if not OPENAI_API_KEY or not client:
        logger.warning("OpenAI API key not configured, skipping LLM invocation")
        return None
    
    try:
        model = os.getenv("LLM_MODEL", "gpt-4.1")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise assistant analyzing video generation anomalies."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM invocation error: {e}")
        return f"LLM analysis failed: {str(e)}"


def emit_metric(metric_name: str, value: float, unit: str = 'Count'):
    """Emit a CloudWatch metric."""
    try:
        cloudwatch.put_metric_data(
            Namespace='Reconciler',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': unit,
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
    except Exception as e:
        logger.error(f"Failed to emit metric {metric_name}: {e}")