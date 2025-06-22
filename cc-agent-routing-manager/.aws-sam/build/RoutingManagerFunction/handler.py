"""
Video Job Routing Manager Lambda Handler
Routes video.job.submitted events to appropriate provider queues
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid

import boto3
from botocore.exceptions import ClientError

from rules import RoutingRuleEngine

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
events_client = boto3.client('events')
cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

# Environment variables
STAGE = os.environ.get('STAGE', 'dev')
REGION = os.environ.get('AWS_REGION', 'us-east-1')
FAL_QUEUE_URL = os.environ.get('FAL_QUEUE_URL')
REPLICATE_QUEUE_URL = os.environ.get('REPLICATE_QUEUE_URL')
JOBS_TABLE_NAME = f"Jobs-{STAGE}"

# Initialize rule engine
rule_engine = RoutingRuleEngine()

# Queue mapping
QUEUE_URLS = {
    "fal": FAL_QUEUE_URL,
    "replicate": REPLICATE_QUEUE_URL
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for video job routing.
    
    Processes video.job.submitted events from EventBridge and routes them
    to appropriate provider queues based on rules.
    
    Args:
        event: EventBridge event containing video job
        context: Lambda context
        
    Returns:
        Response dict with status
    """
    try:
        # Handle EventBridge scheduled events (heartbeat)
        if event.get('source') == 'aws.events' and event.get('detail-type') == 'Scheduled Event':
            return handle_heartbeat()
        
        # Extract video job from EventBridge event
        if 'detail' in event:
            video_job = event['detail']
        else:
            # Direct invocation for testing
            video_job = event
        
        logger.info(f"Processing video job: {json.dumps(video_job)}")
        
        # Validate job
        validation_error = rule_engine.validate_job(video_job)
        if validation_error:
            logger.error(f"Job validation failed: {validation_error}")
            return emit_rejection(video_job.get('jobId', 'unknown'), validation_error)
        
        job_id = video_job['jobId']
        
        # Check for duplicate processing (idempotency)
        if is_job_already_routed(job_id):
            logger.info(f"Job {job_id} already routed, skipping")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'already_processed', 'jobId': job_id})
            }
        
        # Apply routing rules
        provider, model, rejection_reason = rule_engine.evaluate(video_job)
        
        if rejection_reason:
            logger.info(f"Job {job_id} rejected: {rejection_reason}")
            return emit_rejection(job_id, rejection_reason)
        
        # Route to provider queue
        queue_url = QUEUE_URLS.get(provider)
        logger.info(f"Provider: {provider}, Queue URL: {queue_url}")
        logger.info(f"Available queues: {QUEUE_URLS}")
        if not queue_url:
            logger.error(f"No queue URL configured for provider: {provider}")
            return emit_rejection(job_id, f"queue_not_configured:{provider}")
        
        # Send to SQS queue
        try:
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(video_job),
                MessageAttributes={
                    'provider': {'StringValue': provider, 'DataType': 'String'},
                    'model': {'StringValue': model, 'DataType': 'String'},
                    'jobId': {'StringValue': job_id, 'DataType': 'String'}
                }
            )
            logger.info(f"Job {job_id} sent to {provider} queue")
        except Exception as e:
            logger.error(f"Failed to send job to SQS: {str(e)}")
            return emit_rejection(job_id, f"queue_error:{str(e)}")
        
        # Record routing in DynamoDB
        record_routing_decision(job_id, provider, model, queue_url)
        
        # Emit success event
        emit_routed_event(job_id, provider, model, queue_url)
        
        # Send metrics
        send_routing_metrics(provider, True)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'routed',
                'jobId': job_id,
                'provider': provider,
                'model': model
            })
        }
        
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {str(e)}", exc_info=True)
        send_routing_metrics('error', False)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


def handle_heartbeat() -> Dict[str, Any]:
    """Send heartbeat metric to CloudWatch"""
    try:
        cloudwatch.put_metric_data(
            Namespace='Agent/RoutingManager',
            MetricData=[
                {
                    'MetricName': 'Heartbeat',
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc)
                }
            ]
        )
        logger.info("Heartbeat sent successfully")
        return {'statusCode': 200, 'body': 'Heartbeat sent'}
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {str(e)}")
        return {'statusCode': 500, 'body': 'Heartbeat failed'}


def is_job_already_routed(job_id: str) -> bool:
    """
    Check if job has already been routed (idempotency check).
    
    Args:
        job_id: Unique job identifier
        
    Returns:
        True if job was already processed
    """
    try:
        table = dynamodb.Table(JOBS_TABLE_NAME)
        response = table.get_item(
            Key={'jobId': job_id},
            ProjectionExpression='#s',
            ExpressionAttributeNames={'#s': 'status'}
        )
        
        if 'Item' in response:
            status = response['Item'].get('status')
            return status in ['ROUTED', 'PROCESSING', 'COMPLETED']
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking job status: {str(e)}")
        # Conservative approach: assume not routed to avoid skipping
        return False


def record_routing_decision(job_id: str, provider: str, model: str, queue_url: str):
    """
    Record routing decision in DynamoDB Jobs table.
    
    Args:
        job_id: Job identifier
        provider: Selected provider
        model: Selected model
        queue_url: Target queue URL
    """
    try:
        table = dynamodb.Table(JOBS_TABLE_NAME)
        table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #s = :status, provider = :provider, model = :model, '
                           'routedAt = :ts, routedBy = :agent, #q = :queue',
            ExpressionAttributeNames={
                '#s': 'status',
                '#q': 'queue'
            },
            ExpressionAttributeValues={
                ':status': 'ROUTED',
                ':provider': provider,
                ':model': model,
                ':ts': datetime.now(timezone.utc).isoformat(),
                ':agent': 'RoutingManager',
                ':queue': queue_url.split('/')[-1]  # Just queue name
            }
        )
        logger.info(f"Recorded routing decision for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to record routing decision: {str(e)}")
        # Don't fail the request if recording fails


def emit_routed_event(job_id: str, provider: str, model: str, queue_url: str):
    """
    Emit video.job.routed event to EventBridge.
    
    Args:
        job_id: Job identifier
        provider: Selected provider
        model: Selected model
        queue_url: Target queue URL
    """
    try:
        event_detail = {
            'jobId': job_id,
            'provider': provider,
            'model': model,
            'queue': queue_url.split('/')[-1],
            'routedBy': 'RoutingManager',
            'ts': datetime.now(timezone.utc).isoformat()
        }
        
        events_client.put_events(
            Entries=[
                {
                    'Source': 'routing.manager',
                    'DetailType': 'video.job.routed',
                    'Detail': json.dumps(event_detail)
                }
            ]
        )
        logger.info(f"Emitted video.job.routed event for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to emit routed event: {str(e)}")


def emit_rejection(job_id: str, reason: str) -> Dict[str, Any]:
    """
    Emit video.job.rejected event and return error response.
    
    Args:
        job_id: Job identifier
        reason: Rejection reason
        
    Returns:
        Lambda response
    """
    try:
        # Update job status in DynamoDB
        table = dynamodb.Table(JOBS_TABLE_NAME)
        table.update_item(
            Key={'jobId': job_id},
            UpdateExpression='SET #s = :status, rejectionReason = :reason, rejectedAt = :ts',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'REJECTED',
                ':reason': reason,
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Emit rejection event
        event_detail = {
            'jobId': job_id,
            'status': 'rejected',
            'reason': reason,
            'ts': datetime.now(timezone.utc).isoformat()
        }
        
        events_client.put_events(
            Entries=[
                {
                    'Source': 'routing.manager',
                    'DetailType': 'video.job.rejected',
                    'Detail': json.dumps(event_detail)
                }
            ]
        )
        
        logger.info(f"Emitted video.job.rejected event for job {job_id}")
        
    except Exception as e:
        logger.error(f"Failed to handle rejection: {str(e)}")
    
    return {
        'statusCode': 400,
        'body': json.dumps({
            'status': 'rejected',
            'jobId': job_id,
            'reason': reason
        })
    }


def send_routing_metrics(provider: str, success: bool):
    """
    Send routing metrics to CloudWatch.
    
    Args:
        provider: Target provider
        success: Whether routing succeeded
    """
    try:
        metrics = [
            {
                'MetricName': 'RoutingAttempts',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'Provider', 'Value': provider},
                    {'Name': 'Success', 'Value': str(success)},
                    {'Name': 'Stage', 'Value': STAGE}
                ]
            }
        ]
        
        cloudwatch.put_metric_data(
            Namespace='VideoJobRouting',
            MetricData=metrics
        )
    except Exception as e:
        logger.error(f"Failed to send metrics: {str(e)}")


# Health check handler for direct invocation
def health_check(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status
    """
    return handle_heartbeat()