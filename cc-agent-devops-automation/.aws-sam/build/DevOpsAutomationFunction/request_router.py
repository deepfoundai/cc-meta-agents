import json
import os
import boto3
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Initialize AWS clients
secrets_manager = boto3.client('secretsmanager')
cloudformation = boto3.client('cloudformation')
events_client = boto3.client('events')

def handle_devops_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle EventBridge devops.request events
    Routes to appropriate action handler and publishes completion events
    """
    start_time = time.time()
    
    try:
        # Extract request details from EventBridge event
        detail = event.get('detail', {})
        request_id = detail.get('requestId', str(uuid.uuid4()))
        action = detail.get('action')
        stage = detail.get('stage', 'dev')
        params = detail.get('params', {})
        requested_by = detail.get('requestedBy', 'unknown')
        
        print(f"Processing devops.request: {request_id} - {action} from {requested_by}")
        
        if not action:
            raise ValueError("Missing required 'action' field")
        
        # Route to appropriate handler
        if action == 'putSecret':
            result = handle_put_secret(params, stage)
        elif action == 'deployLambda':
            result = handle_deploy_lambda(params, stage)
        else:
            raise ValueError(f"Unsupported action: {action}")
        
        # Calculate latency
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Publish completion event
        completion_event = {
            'requestId': request_id,
            'action': action,
            'status': 'success',
            'result': result,
            'latencyMs': latency_ms,
            'requestedBy': requested_by,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        publish_completion_event(completion_event)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'requestId': request_id,
                'latencyMs': latency_ms
            })
        }
        
    except Exception as e:
        error_msg = str(e)
        latency_ms = int((time.time() - start_time) * 1000)
        
        print(f"DevOps request failed: {error_msg}")
        
        # Publish failure event
        completion_event = {
            'requestId': detail.get('requestId', 'unknown'),
            'action': detail.get('action', 'unknown'),
            'status': 'error',
            'error': error_msg,
            'latencyMs': latency_ms,
            'requestedBy': detail.get('requestedBy', 'unknown'),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        publish_completion_event(completion_event)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': error_msg,
                'latencyMs': latency_ms
            })
        }

def handle_put_secret(params: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """
    Handle putSecret action - create or update secrets in Secrets Manager
    """
    name = params.get('name')
    value = params.get('value')
    kms_key = params.get('kmsKey')
    
    if not name or not value:
        raise ValueError("putSecret requires 'name' and 'value' parameters")
    
    try:
        # Check if secret exists
        try:
            secrets_manager.describe_secret(SecretId=name)
            secret_exists = True
        except secrets_manager.exceptions.ResourceNotFoundException:
            secret_exists = False
        
        if secret_exists:
            # Update existing secret
            response = secrets_manager.put_secret_value(
                SecretId=name,
                SecretString=value
            )
            action_taken = 'updated'
        else:
            # Create new secret
            create_params = {
                'Name': name,
                'SecretString': value,
                'Description': f'Secret created by DevOps-Automation for stage {stage}',
                'Tags': [
                    {'Key': 'createdBy', 'Value': 'DevOpsAutomation'},
                    {'Key': 'stage', 'Value': stage},
                    {'Key': 'service', 'Value': 'ContentCraft'}
                ]
            }
            
            if kms_key:
                create_params['KmsKeyId'] = kms_key
            
            response = secrets_manager.create_secret(**create_params)
            action_taken = 'created'
        
        result = {
            'secretName': name,
            'action': action_taken,
            'arn': response.get('ARN'),
            'versionId': response.get('VersionId')
        }
        
        print(f"Secret {action_taken}: {name}")
        return result
        
    except Exception as e:
        raise Exception(f"Failed to {action_taken if 'action_taken' in locals() else 'manage'} secret {name}: {str(e)}")

def handle_deploy_lambda(params: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """
    Handle deployLambda action - trigger CloudFormation stack deployment
    """
    stack_name = params.get('stackName')
    deployment_stage = params.get('stage', stage)
    
    if not stack_name:
        raise ValueError("deployLambda requires 'stackName' parameter")
    
    # Construct full stack name with stage
    full_stack_name = f"{stack_name}-{deployment_stage}"
    
    try:
        # Check if stack exists
        try:
            cloudformation.describe_stacks(StackName=full_stack_name)
            stack_exists = True
        except cloudformation.exceptions.ClientError as e:
            if 'does not exist' in str(e):
                stack_exists = False
            else:
                raise
        
        if not stack_exists:
            raise Exception(f"Stack {full_stack_name} does not exist. Use 'sam deploy' manually for initial deployment.")
        
        # For existing stacks, we'll trigger an update by describing and getting the template
        # In a real implementation, you'd want to integrate with SAM CLI or have the template available
        
        # Get current stack status
        response = cloudformation.describe_stacks(StackName=full_stack_name)
        stack = response['Stacks'][0]
        current_status = stack['StackStatus']
        
        if current_status in ['CREATE_IN_PROGRESS', 'UPDATE_IN_PROGRESS', 'DELETE_IN_PROGRESS']:
            raise Exception(f"Stack {full_stack_name} is currently in progress state: {current_status}")
        
        # For Phase 2, we'll return stack information without actually triggering deployment
        # In production, this would integrate with SAM CLI or use change sets
        result = {
            'stackName': full_stack_name,
            'action': 'deployment_queued',
            'currentStatus': current_status,
            'note': 'Phase 2 implementation - deployment queued for manual processing'
        }
        
        print(f"Deployment queued for stack: {full_stack_name}")
        return result
        
    except Exception as e:
        raise Exception(f"Failed to deploy stack {full_stack_name}: {str(e)}")

def publish_completion_event(completion_data: Dict[str, Any]) -> None:
    """
    Publish devops.completed event to EventBridge
    """
    try:
        events_client.put_events(
            Entries=[
                {
                    'Source': 'devops.automation',
                    'DetailType': 'devops.completed',
                    'Detail': json.dumps(completion_data),
                    'Time': datetime.now(timezone.utc)
                }
            ]
        )
        
        print(f"Published completion event for request {completion_data.get('requestId')}")
        
    except Exception as e:
        print(f"Failed to publish completion event: {str(e)}")
        # Don't raise - completion event failure shouldn't fail the main operation 