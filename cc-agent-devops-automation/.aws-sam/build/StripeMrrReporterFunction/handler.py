import json
import os
import subprocess
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, List

# Import request router for EventBridge events
from request_router import handle_devops_request

# Initialize AWS clients
cloudwatch = boto3.client('cloudwatch')
ssm = boto3.client('ssm')

# Agent configuration
AGENT_NAME = "DevOpsAutomation"
HEARTBEAT_NAMESPACE = f"Agent/{AGENT_NAME}"


def publish_heartbeat_metric(success: bool = True):
    """Publish 5-minute heartbeat metric to CloudWatch"""
    try:
        cloudwatch.put_metric_data(
            Namespace=HEARTBEAT_NAMESPACE,
            MetricData=[
                {
                    'MetricName': 'Heartbeat',
                    'Value': 1 if success else 0,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc)
                }
            ]
        )
        print(f"Published heartbeat metric: {HEARTBEAT_NAMESPACE}/Heartbeat = {1 if success else 0}")
    except Exception as e:
        print(f"Error publishing heartbeat metric: {str(e)}")


def register_agent_in_ecosystem():
    """Register this agent in the SSM parameter for ecosystem discovery"""
    try:
        # Get current enabled agents
        try:
            response = ssm.get_parameter(Name='/contentcraft/agents/enabled')
            current_agents = response['Parameter']['Value'].split(',')
        except ssm.exceptions.ParameterNotFound:
            current_agents = []
        
        # Add DevOpsAutomation if not already present
        if AGENT_NAME not in current_agents:
            current_agents.append(AGENT_NAME)
            updated_agents = ','.join(current_agents)
            
            ssm.put_parameter(
                Name='/contentcraft/agents/enabled',
                Value=updated_agents,
                Type='String',
                Overwrite=True,
                Description='Comma-separated list of enabled ContentCraft agents'
            )
            print(f"Registered {AGENT_NAME} in ecosystem. Enabled agents: {updated_agents}")
        else:
            print(f"{AGENT_NAME} already registered in ecosystem")
            
    except Exception as e:
        print(f"Error registering agent in ecosystem: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    DevOps automation handler for GitHub and AWS infrastructure tasks
    Enhanced with heartbeat metrics, agent registration, and EventBridge request routing
    """
    try:
        # Check if this is an EventBridge devops.request event
        if event.get('source') and event.get('source').startswith('agent.') and event.get('detail-type') == 'devops.request':
            print("Routing EventBridge devops.request")
            return handle_devops_request(event, context)
        
        # Publish heartbeat metric on every invocation
        publish_heartbeat_metric(success=True)
        
        # Register agent in ecosystem (idempotent)
        register_agent_in_ecosystem()
        
        task_type = event.get('task_type', 'health_check')
        
        if task_type == 'github_repo_check':
            return handle_github_repo_check(event)
        elif task_type == 'workflow_monitor':
            return handle_workflow_monitor(event)
        elif task_type == 'health_check':
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'healthy',
                    'agent': AGENT_NAME,
                    'version': '2.0',
                    'capabilities': [
                        'github_repo_check',
                        'workflow_monitor',
                        'heartbeat_metrics',
                        'agent_registration',
                        'devops_requests',
                        'secret_management',
                        'lambda_deployment'
                    ],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            }
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unknown task type: {task_type}'})
            }
            
    except Exception as e:
        # Publish failure heartbeat
        publish_heartbeat_metric(success=False)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'agent': AGENT_NAME,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }


def handle_github_repo_check(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check GitHub repository settings and configurations
    """
    repo = event.get('repository', 'cc-agent-doc-registry')
    checks_performed = []
    issues_found = []
    
    # Check branch protection
    try:
        result = subprocess.run(
            ['gh', 'api', f'repos/deepfoundai/{repo}/branches/main/protection'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            protection = json.loads(result.stdout)
            if not protection.get('required_pull_request_reviews'):
                issues_found.append('Branch protection missing PR review requirement')
            if 'update-registry' not in str(protection.get('required_status_checks', {})):
                issues_found.append('Missing required status check: update-registry')
            checks_performed.append('branch_protection')
    except Exception as e:
        issues_found.append(f'Branch protection check failed: {str(e)}')
    
    # Check dependabot configuration
    try:
        result = subprocess.run(
            ['gh', 'api', f'repos/deepfoundai/{repo}/contents/.github/dependabot.yml'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            checks_performed.append('dependabot_config')
        else:
            issues_found.append('Dependabot configuration missing')
    except Exception as e:
        issues_found.append(f'Dependabot check failed: {str(e)}')
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'repository': repo,
            'checks_performed': checks_performed,
            'issues_found': issues_found,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    }


def handle_workflow_monitor(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Monitor GitHub Actions workflow runs
    """
    repo = event.get('repository', 'cc-agent-doc-registry')
    workflow = event.get('workflow', 'update-registry.yml')
    
    try:
        # Get latest workflow run
        result = subprocess.run(
            ['gh', 'run', 'list', '--repo', f'deepfoundai/{repo}', 
             '--workflow', workflow, '--limit', '1', '--json', 'status,conclusion,createdAt'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            runs = json.loads(result.stdout)
            if runs:
                latest_run = runs[0]
                if latest_run.get('conclusion') == 'failure':
                    # Create issue for failed workflow
                    issue_body = f"Workflow {workflow} failed at {latest_run.get('createdAt')}"
                    subprocess.run([
                        'gh', 'issue', 'create', '--repo', f'deepfoundai/{repo}',
                        '--title', f'Workflow failure: {workflow}',
                        '--body', issue_body
                    ])
                    
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'workflow': workflow,
                        'status': latest_run.get('status'),
                        'conclusion': latest_run.get('conclusion'),
                        'action_taken': 'issue_created' if latest_run.get('conclusion') == 'failure' else None
                    })
                }
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'workflow': workflow,
                'status': 'no_runs_found'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }