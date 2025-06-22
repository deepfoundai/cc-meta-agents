"""
Health monitor for CC Agent Routing Manager.
Periodically checks health of all registered agents.
"""

import json
import os
import time
from typing import Dict, Any, List
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import concurrent.futures

# Set up logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize AWS clients
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
HEALTH_TABLE = os.environ.get('HEALTH_TABLE')
AGENT_ENDPOINTS = json.loads(os.environ.get('AGENT_ENDPOINTS', '{}'))
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Health check configuration
HEALTH_CHECK_TIMEOUT = 5  # seconds
MAX_WORKERS = 5  # concurrent health checks


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for scheduled health monitoring.
    
    Args:
        event: CloudWatch Events scheduled event
        context: Lambda context
        
    Returns:
        Summary of health check results
    """
    logger.info("Starting health monitor check")
    
    try:
        # Check all agents concurrently
        health_results = check_all_agents_health()
        
        # Update health table
        update_health_records(health_results)
        
        # Send health metrics
        send_health_metrics(health_results)
        
        # Log summary
        healthy_count = sum(1 for r in health_results if r['healthy'])
        total_count = len(health_results)
        
        logger.info(f"Health check complete: {healthy_count}/{total_count} agents healthy")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'timestamp': datetime.utcnow().isoformat(),
                'healthy_agents': healthy_count,
                'total_agents': total_count,
                'results': health_results
            })
        }
        
    except Exception as e:
        logger.error(f"Error in health monitor: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def check_all_agents_health() -> List[Dict[str, Any]]:
    """
    Check health of all registered agents concurrently.
    
    Returns:
        List of health check results
    """
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit health checks for all agents
        future_to_agent = {
            executor.submit(check_agent_health, agent_id, function_arn): agent_id
            for agent_id, function_arn in AGENT_ENDPOINTS.items()
        }
        
        # Collect results
        for future in concurrent.futures.as_completed(future_to_agent):
            agent_id = future_to_agent[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Error checking health for agent {agent_id}: {str(e)}")
                results.append({
                    'agentId': agent_id,
                    'healthy': False,
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                })
                
    return results


def check_agent_health(agent_id: str, function_arn: str) -> Dict[str, Any]:
    """
    Check health of a specific agent.
    
    Args:
        agent_id: Agent identifier
        function_arn: Lambda function ARN
        
    Returns:
        Health check result
    """
    start_time = time.time()
    
    try:
        # Invoke agent with health check request
        response = lambda_client.invoke(
            FunctionName=function_arn,
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'httpMethod': 'GET',
                'path': '/health',
                'headers': {'X-Health-Check': 'true'}
            })
        )
        
        # Check response
        status_code = response.get('StatusCode', 0)
        
        if status_code == 200:
            payload = json.loads(response['Payload'].read())
            
            # Parse health response
            if isinstance(payload, dict) and payload.get('statusCode') == 200:
                body = json.loads(payload.get('body', '{}'))
                is_healthy = body.get('status') == 'healthy'
                
                return {
                    'agentId': agent_id,
                    'healthy': is_healthy,
                    'status': body.get('status', 'unknown'),
                    'responseTime': (time.time() - start_time) * 1000,
                    'timestamp': datetime.utcnow().isoformat(),
                    'details': body
                }
            else:
                return {
                    'agentId': agent_id,
                    'healthy': False,
                    'error': 'Invalid health response format',
                    'responseTime': (time.time() - start_time) * 1000,
                    'timestamp': datetime.utcnow().isoformat()
                }
        else:
            return {
                'agentId': agent_id,
                'healthy': False,
                'error': f'Lambda returned status code {status_code}',
                'responseTime': (time.time() - start_time) * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
            
    except ClientError as e:
        error_code = e.response['Error']['Code']
        return {
            'agentId': agent_id,
            'healthy': False,
            'error': f'AWS error: {error_code}',
            'responseTime': (time.time() - start_time) * 1000,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            'agentId': agent_id,
            'healthy': False,
            'error': str(e),
            'responseTime': (time.time() - start_time) * 1000,
            'timestamp': datetime.utcnow().isoformat()
        }


def update_health_records(health_results: List[Dict[str, Any]]):
    """
    Update health records in DynamoDB.
    
    Args:
        health_results: List of health check results
    """
    table = dynamodb.Table(HEALTH_TABLE)
    
    with table.batch_writer() as batch:
        for result in health_results:
            try:
                # Calculate error rate from recent history
                error_rate = calculate_error_rate(result['agentId'])
                
                item = {
                    'agentId': result['agentId'],
                    'status': 'healthy' if result['healthy'] else 'unhealthy',
                    'lastCheck': result['timestamp'],
                    'responseTime': result.get('responseTime', 0),
                    'errorRate': error_rate,
                    'error': result.get('error'),
                    'details': result.get('details', {}),
                    'ttl': int(time.time()) + (24 * 60 * 60)  # 24 hour TTL
                }
                
                batch.put_item(Item=item)
                
            except Exception as e:
                logger.error(f"Error updating health record for {result['agentId']}: {str(e)}")


def calculate_error_rate(agent_id: str) -> float:
    """
    Calculate recent error rate for an agent.
    
    Args:
        agent_id: Agent identifier
        
    Returns:
        Error rate as decimal (0.0 to 1.0)
    """
    try:
        # This is a simplified calculation
        # In production, would query routing history for actual error rate
        return 0.0
    except Exception:
        return 0.0


def send_health_metrics(health_results: List[Dict[str, Any]]):
    """
    Send health metrics to CloudWatch.
    
    Args:
        health_results: List of health check results
    """
    try:
        metrics = []
        
        for result in health_results:
            # Health status metric
            metrics.append({
                'MetricName': 'AgentHealth',
                'Value': 1 if result['healthy'] else 0,
                'Unit': 'None',
                'Dimensions': [
                    {'Name': 'Agent', 'Value': result['agentId']},
                    {'Name': 'Environment', 'Value': ENVIRONMENT}
                ]
            })
            
            # Response time metric
            if 'responseTime' in result:
                metrics.append({
                    'MetricName': 'HealthCheckResponseTime',
                    'Value': result['responseTime'],
                    'Unit': 'Milliseconds',
                    'Dimensions': [
                        {'Name': 'Agent', 'Value': result['agentId']},
                        {'Name': 'Environment', 'Value': ENVIRONMENT}
                    ]
                })
                
        # Send metrics in batches (CloudWatch limit is 20 metrics per request)
        for i in range(0, len(metrics), 20):
            batch = metrics[i:i+20]
            cloudwatch.put_metric_data(
                Namespace='CCAgentHealth',
                MetricData=batch
            )
            
    except Exception as e:
        logger.error(f"Error sending health metrics: {str(e)}")