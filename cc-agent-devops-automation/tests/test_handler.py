import json
import pytest
from unittest.mock import patch, MagicMock, Mock
from src.handler import (
    lambda_handler, 
    handle_github_repo_check, 
    handle_workflow_monitor,
    publish_heartbeat_metric,
    register_agent_in_ecosystem,
    AGENT_NAME,
    HEARTBEAT_NAMESPACE
)


class TestDevOpsHandler:
    
    @patch('src.handler.publish_heartbeat_metric')
    @patch('src.handler.register_agent_in_ecosystem')
    def test_health_check(self, mock_register, mock_heartbeat):
        """Test health check returns success with enhanced response"""
        event = {'task_type': 'health_check'}
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'healthy'
        assert body['agent'] == AGENT_NAME
        assert body['version'] == '1.0'
        assert 'capabilities' in body
        assert 'heartbeat_metrics' in body['capabilities']
        assert 'agent_registration' in body['capabilities']
        
        # Verify heartbeat and registration were called
        mock_heartbeat.assert_called_once_with(success=True)
        mock_register.assert_called_once()
    
    @patch('src.handler.cloudwatch')
    def test_publish_heartbeat_metric_success(self, mock_cloudwatch):
        """Test successful heartbeat metric publication"""
        publish_heartbeat_metric(success=True)
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        
        assert call_args[1]['Namespace'] == HEARTBEAT_NAMESPACE
        assert call_args[1]['MetricData'][0]['MetricName'] == 'Heartbeat'
        assert call_args[1]['MetricData'][0]['Value'] == 1
        assert call_args[1]['MetricData'][0]['Unit'] == 'Count'
    
    @patch('src.handler.cloudwatch')
    def test_publish_heartbeat_metric_failure(self, mock_cloudwatch):
        """Test failure heartbeat metric publication"""
        publish_heartbeat_metric(success=False)
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        
        assert call_args[1]['MetricData'][0]['Value'] == 0
    
    @patch('src.handler.ssm')
    def test_register_agent_new(self, mock_ssm):
        """Test registering agent when not already present"""
        # Mock existing parameter with other agents
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'CostSentinel,DocRegistry'}
        }
        
        register_agent_in_ecosystem()
        
        mock_ssm.put_parameter.assert_called_once()
        call_args = mock_ssm.put_parameter.call_args
        
        assert call_args[1]['Name'] == '/contentcraft/agents/enabled'
        assert AGENT_NAME in call_args[1]['Value']
        assert 'CostSentinel' in call_args[1]['Value']
    
    @patch('src.handler.ssm')
    def test_register_agent_already_exists(self, mock_ssm):
        """Test registering agent when already present"""
        # Mock existing parameter with DevOpsAutomation already included
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': f'CostSentinel,{AGENT_NAME}'}
        }
        
        register_agent_in_ecosystem()
        
        # Should not call put_parameter if already registered
        mock_ssm.put_parameter.assert_not_called()
    
    @patch('src.handler.ssm')
    def test_register_agent_no_existing_parameter(self, mock_ssm):
        """Test registering agent when no parameter exists"""
        # Mock parameter not found
        from botocore.exceptions import ClientError
        mock_ssm.get_parameter.side_effect = ClientError(
            {'Error': {'Code': 'ParameterNotFound'}}, 'GetParameter'
        )
        
        register_agent_in_ecosystem()
        
        mock_ssm.put_parameter.assert_called_once()
        call_args = mock_ssm.put_parameter.call_args
        
        assert call_args[1]['Value'] == AGENT_NAME
    
    @patch('src.handler.publish_heartbeat_metric')
    @patch('src.handler.register_agent_in_ecosystem')
    def test_lambda_handler_exception_handling(self, mock_register, mock_heartbeat):
        """Test lambda handler publishes failure heartbeat on exception"""
        # Cause an exception in registration
        mock_register.side_effect = Exception("Test error")
        
        event = {'task_type': 'health_check'}
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'error' in body
        assert body['agent'] == AGENT_NAME
        
        # Should have called heartbeat with failure
        mock_heartbeat.assert_called_with(success=False)
    
    def test_unknown_task_type(self):
        """Test unknown task type returns error"""
        event = {'task_type': 'unknown'}
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    @patch('subprocess.run')
    def test_github_repo_check_success(self, mock_run):
        """Test successful GitHub repo check"""
        # Mock successful branch protection check
        protection_response = MagicMock()
        protection_response.returncode = 0
        protection_response.stdout = json.dumps({
            'required_pull_request_reviews': {'required_approving_review_count': 1},
            'required_status_checks': {'contexts': ['update-registry']}
        })
        
        # Mock successful dependabot check
        dependabot_response = MagicMock()
        dependabot_response.returncode = 0
        
        mock_run.side_effect = [protection_response, dependabot_response]
        
        event = {'repository': 'cc-agent-doc-registry'}
        response = handle_github_repo_check(event)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'branch_protection' in body['checks_performed']
        assert 'dependabot_config' in body['checks_performed']
        assert len(body['issues_found']) == 0
    
    @patch('subprocess.run')
    def test_github_repo_check_missing_protection(self, mock_run):
        """Test GitHub repo check with missing protections"""
        # Mock branch protection without required checks
        protection_response = MagicMock()
        protection_response.returncode = 0
        protection_response.stdout = json.dumps({})
        
        # Mock missing dependabot
        dependabot_response = MagicMock()
        dependabot_response.returncode = 1
        
        mock_run.side_effect = [protection_response, dependabot_response]
        
        event = {'repository': 'cc-agent-doc-registry'}
        response = handle_github_repo_check(event)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['issues_found']) > 0
        assert any('PR review' in issue for issue in body['issues_found'])
        assert any('Dependabot' in issue for issue in body['issues_found'])
    
    @patch('subprocess.run')
    def test_workflow_monitor_success(self, mock_run):
        """Test workflow monitor with successful run"""
        # Mock successful workflow run
        list_response = MagicMock()
        list_response.returncode = 0
        list_response.stdout = json.dumps([{
            'status': 'completed',
            'conclusion': 'success',
            'createdAt': '2024-01-20T06:00:00Z'
        }])
        
        mock_run.return_value = list_response
        
        event = {
            'repository': 'cc-agent-doc-registry',
            'workflow': 'update-registry.yml'
        }
        response = handle_workflow_monitor(event)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'completed'
        assert body['conclusion'] == 'success'
        assert body['action_taken'] is None
    
    @patch('subprocess.run')
    def test_workflow_monitor_failure_creates_issue(self, mock_run):
        """Test workflow monitor creates issue on failure"""
        # Mock failed workflow run
        list_response = MagicMock()
        list_response.returncode = 0
        list_response.stdout = json.dumps([{
            'status': 'completed',
            'conclusion': 'failure',
            'createdAt': '2024-01-20T06:00:00Z'
        }])
        
        # Mock issue creation
        issue_response = MagicMock()
        issue_response.returncode = 0
        
        mock_run.side_effect = [list_response, issue_response]
        
        event = {
            'repository': 'cc-agent-doc-registry',
            'workflow': 'update-registry.yml'
        }
        response = handle_workflow_monitor(event)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['conclusion'] == 'failure'
        assert body['action_taken'] == 'issue_created'
        
        # Verify issue creation was called
        assert mock_run.call_count == 2
        issue_call = mock_run.call_args_list[1]
        assert 'issue' in str(issue_call)
        assert 'create' in str(issue_call)