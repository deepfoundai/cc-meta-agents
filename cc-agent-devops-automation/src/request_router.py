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
        elif action == 'agentWork':
            result = handle_agent_work(params, detail)
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

def handle_agent_work(params: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle agentWork action - route GitHub issue work to appropriate agent
    """
    import base64
    
    # For agentWork, the data is in payload, not params
    payload = detail.get('payload', params)  # Fallback to params for backward compatibility
    
    agent = detail.get('agent')
    spec_b64 = payload.get('spec', '')
    deadline = payload.get('deadline', 'none')
    deps_b64 = payload.get('deps', '')
    issue_number = payload.get('issueNumber', 'unknown')
    issue_title = payload.get('issueTitle', 'Untitled Task')
    issue_url = payload.get('issueUrl', '')
    
    if not agent:
        raise ValueError("agentWork requires 'agent' field")
    
    if not spec_b64:
        raise ValueError("agentWork requires 'spec' field")
    
    try:
        # Decode the base64-encoded specification
        spec = base64.b64decode(spec_b64).decode('utf-8')
        deps = base64.b64decode(deps_b64).decode('utf-8') if deps_b64 else ''
        
        print(f"Agent work request for {agent}:")
        print(f"  Issue: #{issue_number} - {issue_title}")
        print(f"  Spec: {spec[:100]}..." if len(spec) > 100 else f"  Spec: {spec}")
        print(f"  Deadline: {deadline}")
        print(f"  Dependencies: {deps}" if deps else "  Dependencies: None")
        
        # Route to specific agent based on agent name
        if agent == 'DevOpsAutomation':
            result = handle_devops_agent_work(spec, issue_number, issue_title, deadline, deps)
        else:
            # For other agents, publish to their specific EventBridge pattern
            result = route_to_agent(agent, spec, issue_number, issue_title, deadline, deps, issue_url)
        
        return {
            'agent': agent,
            'issueNumber': issue_number,
            'action': 'work_dispatched',
            'result': result
        }
        
    except Exception as e:
        raise Exception(f"Failed to handle agent work for {agent}: {str(e)}")

def handle_devops_agent_work(spec: str, issue_number: str, issue_title: str, deadline: str, deps: str) -> Dict[str, Any]:
    """
    Handle work specifically assigned to DevOpsAutomation agent
    """
    print(f"Processing DevOps work from issue #{issue_number}")
    
    # Simple pattern matching for common DevOps tasks
    spec_lower = spec.lower()
    
    if 'deploy' in spec_lower and 'lambda' in spec_lower:
        # Extract stack name from spec if possible
        lines = spec.split('\n')
        stack_name = None
        for line in lines:
            if 'stack' in line.lower():
                # Try to extract stack name from patterns like "stack: cc-agent-xyz" or "deploy cc-agent-xyz"
                import re
                match = re.search(r'(cc-agent-[\w-]+)', line)
                if match:
                    stack_name = match.group(1)
                    break
        
        if stack_name:
            print(f"Deploying stack: {stack_name}")
            return handle_deploy_lambda({'stackName': stack_name}, 'prod')
        else:
            return {'action': 'manual_review_required', 'reason': 'Could not extract stack name from spec'}
    
    elif 'secret' in spec_lower and ('create' in spec_lower or 'update' in spec_lower):
        return {'action': 'manual_review_required', 'reason': 'Secret operations require manual review for security'}
    
    else:
        # Generic DevOps task - mark as processed but requiring manual follow-up
        return {
            'action': 'acknowledged',
            'note': f'DevOps task from issue #{issue_number} acknowledged and queued for manual processing',
            'spec_preview': spec[:200] + '...' if len(spec) > 200 else spec
        }

def route_to_agent(agent: str, spec: str, issue_number: str, issue_title: str, deadline: str, deps: str, issue_url: str) -> Dict[str, Any]:
    """
    Route work to other agents via EventBridge
    """
    agent_event_mapping = {
        'CostSentinel': 'cost.sentinel.request',
        'FalInvoker': 'fal.invoker.request', 
        'RoutingManager': 'routing.manager.request',
        'PromptCurator': 'prompt.curator.request',
        'CreditReconciler': 'credit.reconciler.request',
        'DocRegistry': 'doc.registry.request',
        'MrrReporter': 'mrr.reporter.request'
    }
    
    event_type = agent_event_mapping.get(agent)
    if not event_type:
        raise ValueError(f"Unknown agent: {agent}")
    
    # Publish agent-specific work event
    work_event = {
        'Source': 'github.issues',
        'DetailType': event_type,
        'Detail': json.dumps({
            'workType': 'github_issue',
            'issueNumber': issue_number,
            'issueTitle': issue_title,
            'issueUrl': issue_url,
            'spec': spec,
            'deadline': deadline,
            'dependencies': deps,
            'requestedAt': datetime.now(timezone.utc).isoformat()
        })
    }
    
    try:
        events_client.put_events(Entries=[work_event])
        print(f"Routed work to {agent} via {event_type}")
        
        return {
            'action': 'routed_to_agent',
            'agent': agent,
            'eventType': event_type,
            'issueNumber': issue_number
        }
        
    except Exception as e:
        raise Exception(f"Failed to route work to {agent}: {str(e)}")

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