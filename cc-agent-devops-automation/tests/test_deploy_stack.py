"""
Unit tests for the deploy_stack handler
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
import subprocess

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from handlers.deploy_stack import (
    handle_deploy_stack, _run_sam_build, _run_sam_deploy, _get_stack_id
)


class TestDeployStack:
    
    def test_handle_deploy_stack_success(self):
        """Test successful stack deployment"""
        request_id = "test-request-123"
        payload = {
            "stackName": "test-stack",
            "samTemplatePath": "template.yaml",
            "parameters": {"Environment": "prod"}
        }
        stage = "prod"
        
        with patch('os.path.exists', return_value=True):
            with patch('handlers.deploy_stack._run_sam_build', return_value=(True, "Build successful")):
                with patch('handlers.deploy_stack._run_sam_deploy', return_value=(True, "Deploy successful")):
                    with patch('handlers.deploy_stack._get_stack_id', return_value="arn:aws:cloudformation:us-east-1:123:stack/test-stack-prod"):
                        result = handle_deploy_stack(request_id, payload, stage)
                        
                        assert result['status'] == 'success'
                        assert result['requestId'] == request_id
                        assert result['action'] == 'deploy_stack'
                        assert result['result']['stackName'] == 'test-stack'
                        assert result['result']['stage'] == 'prod'
                        assert 'latencyMs' in result
    
    def test_handle_deploy_stack_missing_stack_name(self):
        """Test error when stackName is missing"""
        request_id = "test-request-123"
        payload = {"samTemplatePath": "template.yaml"}
        stage = "prod"
        
        result = handle_deploy_stack(request_id, payload, stage)
        
        assert result['status'] == 'error'
        assert result['reason'] == 'missing_parameter'
        assert 'stackName is required' in result['error']
    
    def test_handle_deploy_stack_template_not_found(self):
        """Test error when SAM template doesn't exist"""
        request_id = "test-request-123"
        payload = {
            "stackName": "test-stack",
            "samTemplatePath": "nonexistent.yaml"
        }
        stage = "prod"
        
        with patch('os.path.exists', return_value=False):
            result = handle_deploy_stack(request_id, payload, stage)
            
            assert result['status'] == 'error'
            assert result['reason'] == 'template_not_found'
            assert 'SAM template not found' in result['error']
    
    def test_handle_deploy_stack_build_failure(self):
        """Test error when sam build fails"""
        request_id = "test-request-123"
        payload = {"stackName": "test-stack"}
        stage = "prod"
        
        with patch('os.path.exists', return_value=True):
            with patch('handlers.deploy_stack._run_sam_build', return_value=(False, "Build failed: syntax error")):
                result = handle_deploy_stack(request_id, payload, stage)
                
                assert result['status'] == 'error'
                assert result['reason'] == 'build_failed'
                assert 'Build failed: syntax error' in result['error']
    
    def test_handle_deploy_stack_deploy_failure(self):
        """Test error when sam deploy fails"""
        request_id = "test-request-123"
        payload = {"stackName": "test-stack"}
        stage = "prod"
        
        with patch('os.path.exists', return_value=True):
            with patch('handlers.deploy_stack._run_sam_build', return_value=(True, "Build successful")):
                with patch('handlers.deploy_stack._run_sam_deploy', return_value=(False, "Deploy failed: insufficient permissions")):
                    result = handle_deploy_stack(request_id, payload, stage)
                    
                    assert result['status'] == 'error'
                    assert result['reason'] == 'deploy_failed'
                    assert 'Deploy failed: insufficient permissions' in result['error']


class TestSamBuild:
    
    @patch('subprocess.run')
    def test_run_sam_build_success(self, mock_run):
        """Test successful sam build"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Build successful")
        
        success, output = _run_sam_build("template.yaml")
        
        assert success is True
        assert output == "Build successful"
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_run_sam_build_failure(self, mock_run):
        """Test failed sam build"""
        mock_run.return_value = MagicMock(returncode=1, stderr="Build failed")
        
        success, output = _run_sam_build("template.yaml")
        
        assert success is False
        assert "sam build failed: Build failed" in output
    
    @patch('subprocess.run')
    def test_run_sam_build_timeout(self, mock_run):
        """Test sam build timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired("sam", 300)
        
        success, output = _run_sam_build("template.yaml")
        
        assert success is False
        assert "timed out after 5 minutes" in output


class TestSamDeploy:
    
    @patch('subprocess.run')
    def test_run_sam_deploy_success(self, mock_run):
        """Test successful sam deploy"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Deploy successful")
        
        success, output = _run_sam_deploy("test-stack", "prod", {})
        
        assert success is True
        assert output == "Deploy successful"
        
        # Verify correct command was called
        called_args = mock_run.call_args[0][0]
        assert 'sam' in called_args
        assert 'deploy' in called_args
        assert '--stack-name' in called_args
        assert 'test-stack-prod' in called_args
    
    @patch('subprocess.run')
    def test_run_sam_deploy_with_parameters(self, mock_run):
        """Test sam deploy with parameters"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Deploy successful")
        
        parameters = {"Environment": "prod", "BucketName": "test-bucket"}
        success, output = _run_sam_deploy("test-stack", "prod", parameters)
        
        assert success is True
        
        # Verify parameters were included
        called_args = mock_run.call_args[0][0]
        assert '--parameter-overrides' in called_args
        assert 'Environment=prod' in called_args
        assert 'BucketName=test-bucket' in called_args


class TestGetStackId:
    
    @patch('boto3.client')
    def test_get_stack_id_success(self, mock_boto3):
        """Test successful stack ID retrieval"""
        mock_cf = MagicMock()
        mock_boto3.return_value = mock_cf
        mock_cf.describe_stacks.return_value = {
            'Stacks': [{'StackId': 'arn:aws:cloudformation:us-east-1:123:stack/test-stack-prod/uuid'}]
        }
        
        stack_id = _get_stack_id("test-stack", "prod")
        
        assert stack_id == 'arn:aws:cloudformation:us-east-1:123:stack/test-stack-prod/uuid'
        mock_cf.describe_stacks.assert_called_once_with(StackName='test-stack-prod')
    
    @patch('boto3.client')
    def test_get_stack_id_not_found(self, mock_boto3):
        """Test stack ID when stack not found"""
        mock_cf = MagicMock()
        mock_boto3.return_value = mock_cf
        mock_cf.describe_stacks.side_effect = Exception("Stack not found")
        
        stack_id = _get_stack_id("test-stack", "prod")
        
        assert "arn:aws:cloudformation:us-east-1:UNKNOWN:stack/test-stack-prod" in stack_id 