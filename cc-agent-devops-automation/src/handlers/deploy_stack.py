"""
Deploy Stack Handler

Handles SAM/CloudFormation stack deployments with parameters.
Executes sam build and sam deploy operations with proper error handling.
"""

import json
import subprocess
import time
import os
from typing import Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError


def handle_deploy_stack(request_id: str, payload: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """
    Deploy a SAM/CloudFormation stack.
    
    Args:
        request_id: Unique identifier for this request
        payload: Contains stackName, samTemplatePath, and optional parameters
        stage: Deployment environment (dev/prod)
        
    Returns:
        Completion event with result or error
    """
    start_time = time.time()
    
    try:
        # Validate required parameters
        stack_name = payload.get('stackName')
        if not stack_name:
            return _error_response(request_id, "missing_parameter", "stackName is required", start_time)
        
        sam_template_path = payload.get('samTemplatePath', 'template.yaml')
        parameters = payload.get('parameters', {})
        
        # Ensure template exists
        if not os.path.exists(sam_template_path):
            return _error_response(request_id, "template_not_found", 
                                 f"SAM template not found: {sam_template_path}", start_time)
        
        # Build the stack
        build_result = _run_sam_build(sam_template_path)
        if not build_result[0]:
            return _error_response(request_id, "build_failed", build_result[1], start_time)
        
        # Deploy the stack
        deploy_result = _run_sam_deploy(stack_name, stage, parameters)
        if not deploy_result[0]:
            return _error_response(request_id, "deploy_failed", deploy_result[1], start_time)
        
        # Get stack information
        stack_id = _get_stack_id(stack_name, stage)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "requestId": request_id,
            "action": "deploy_stack",
            "status": "success",
            "result": {
                "stackId": stack_id,
                "stackName": stack_name,
                "stage": stage,
                "templatePath": sam_template_path
            },
            "latencyMs": latency_ms,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
    except Exception as e:
        return _error_response(request_id, "internal_error", str(e), start_time)


def _run_sam_build(template_path: str) -> Tuple[bool, str]:
    """
    Run sam build command.
    
    Returns:
        Tuple of (success, output/error_message)
    """
    try:
        template_dir = os.path.dirname(template_path) or '.'
        result = subprocess.run(
            ['sam', 'build', '--template-file', template_path],
            cwd=template_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, f"sam build failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "sam build timed out after 5 minutes"
    except Exception as e:
        return False, f"sam build error: {str(e)}"


def _run_sam_deploy(stack_name: str, stage: str, parameters: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Run sam deploy command.
    
    Returns:
        Tuple of (success, output/error_message)
    """
    try:
        cmd = [
            'sam', 'deploy',
            '--stack-name', f"{stack_name}-{stage}",
            '--capabilities', 'CAPABILITY_IAM',
            '--no-confirm-changeset',
            '--no-fail-on-empty-changeset'
        ]
        
        # Add parameters if provided
        if parameters:
            param_overrides = []
            for key, value in parameters.items():
                param_overrides.append(f"{key}={value}")
            cmd.extend(['--parameter-overrides'] + param_overrides)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, f"sam deploy failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "sam deploy timed out after 10 minutes"
    except Exception as e:
        return False, f"sam deploy error: {str(e)}"


def _get_stack_id(stack_name: str, stage: str) -> str:
    """
    Get the CloudFormation stack ID.
    
    Returns:
        Stack ARN/ID or empty string if not found
    """
    try:
        cf_client = boto3.client('cloudformation')
        full_stack_name = f"{stack_name}-{stage}"
        
        response = cf_client.describe_stacks(StackName=full_stack_name)
        stacks = response.get('Stacks', [])
        
        if stacks:
            return stacks[0]['StackId']
        else:
            return f"arn:aws:cloudformation:us-east-1:UNKNOWN:stack/{full_stack_name}"
            
    except ClientError:
        return f"arn:aws:cloudformation:us-east-1:UNKNOWN:stack/{stack_name}-{stage}"


def _error_response(request_id: str, reason: str, error_msg: str, start_time: float) -> Dict[str, Any]:
    """
    Generate a standardized error response.
    """
    latency_ms = int((time.time() - start_time) * 1000)
    
    return {
        "requestId": request_id,
        "action": "deploy_stack", 
        "status": "error",
        "error": error_msg,
        "reason": reason,
        "latencyMs": latency_ms,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    } 