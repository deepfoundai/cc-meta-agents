"""
Bootstrap Repo Secrets Handler

Handles bulk creation/update of GitHub Actions secrets for repositories.
Uses GitHub REST API via Personal Access Token from AWS Secrets Manager.
"""

import json
import time
import base64
from typing import Dict, Any, Tuple
import boto3
import requests
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


def handle_bootstrap_repo_secrets(request_id: str, payload: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """
    Bootstrap GitHub Actions secrets for a repository.
    
    Args:
        request_id: Unique identifier for this request
        payload: Contains repo and secrets dict with plain values
        stage: Deployment environment (dev/prod)
        
    Returns:
        Completion event with result or error
    """
    start_time = time.time()
    
    try:
        # Validate required parameters
        repo = payload.get('repo')
        if not repo:
            return _error_response(request_id, "missing_parameter", "repo is required", start_time)
        
        secrets = payload.get('secrets')
        if not secrets or not isinstance(secrets, dict):
            return _error_response(request_id, "missing_parameter", "secrets dict is required", start_time)
        
        # Validate repo format (must be deepfoundai/*)
        if not repo.startswith('deepfoundai/'):
            return _error_response(request_id, "security_violation", 
                                 "Only deepfoundai/* repositories are authorized", start_time)
        
        # Get GitHub token from Secrets Manager
        github_token = _get_github_token()
        if not github_token:
            return _error_response(request_id, "missing_dependency", 
                                 "GitHub token not found in Secrets Manager", start_time)
        
        # Get repository public key for encryption
        public_key = _get_repo_public_key(repo, github_token)
        if not public_key:
            return _error_response(request_id, "api_error", 
                                 f"Could not get public key for repository {repo}", start_time)
        
        # Process each secret
        created_count = 0
        updated_count = 0
        
        for secret_name, secret_value in secrets.items():
            # Encrypt the secret value
            encrypted_value = _encrypt_secret(secret_value, public_key['key'])
            
            # Create/update the secret
            success, is_new = _upsert_secret(repo, secret_name, encrypted_value, 
                                           public_key['key_id'], github_token)
            
            if success:
                if is_new:
                    created_count += 1
                else:
                    updated_count += 1
            else:
                return _error_response(request_id, "api_error", 
                                     f"Failed to set secret {secret_name}", start_time)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "requestId": request_id,
            "action": "bootstrap_repo_secrets",
            "status": "success",
            "result": {
                "repository": repo,
                "created": created_count,
                "updated": updated_count,
                "total": len(secrets)
            },
            "latencyMs": latency_ms,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
    except Exception as e:
        return _error_response(request_id, "internal_error", str(e), start_time)


def _get_github_token() -> str:
    """
    Get GitHub Personal Access Token from AWS Secrets Manager.
    
    Returns:
        GitHub token or empty string if not found
    """
    try:
        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId='/contentcraft/github/token')
        return response['SecretString']
    except ClientError:
        return ""


def _get_repo_public_key(repo: str, github_token: str) -> Dict[str, str]:
    """
    Get repository's public key for secret encryption.
    
    Returns:
        Dict with 'key' and 'key_id' or None if failed
    """
    try:
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(
            f'https://api.github.com/repos/{repo}/actions/secrets/public-key',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                'key': data['key'],
                'key_id': data['key_id']
            }
        else:
            return None
            
    except requests.RequestException:
        return None


def _encrypt_secret(secret_value: str, public_key_b64: str) -> str:
    """
    Encrypt a secret value using the repository's public key.
    
    Returns:
        Base64-encoded encrypted value
    """
    # Decode the public key
    public_key_bytes = base64.b64decode(public_key_b64)
    public_key = serialization.load_der_public_key(public_key_bytes)
    
    # Encrypt the secret
    encrypted = public_key.encrypt(
        secret_value.encode('utf-8'),
        padding.PKCS1v15()
    )
    
    # Return base64-encoded result
    return base64.b64encode(encrypted).decode('utf-8')


def _upsert_secret(repo: str, secret_name: str, encrypted_value: str, 
                   key_id: str, github_token: str) -> Tuple[bool, bool]:
    """
    Create or update a repository secret.
    
    Returns:
        Tuple of (success, is_new)
    """
    try:
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
        
        data = {
            'encrypted_value': encrypted_value,
            'key_id': key_id
        }
        
        response = requests.put(
            f'https://api.github.com/repos/{repo}/actions/secrets/{secret_name}',
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code in [201, 204]:
            # 201 = created, 204 = updated
            return True, response.status_code == 201
        else:
            return False, False
            
    except requests.RequestException:
        return False, False


def _error_response(request_id: str, reason: str, error_msg: str, start_time: float) -> Dict[str, Any]:
    """
    Generate a standardized error response.
    """
    latency_ms = int((time.time() - start_time) * 1000)
    
    return {
        "requestId": request_id,
        "action": "bootstrap_repo_secrets",
        "status": "error",
        "error": error_msg,
        "reason": reason,
        "latencyMs": latency_ms,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    } 