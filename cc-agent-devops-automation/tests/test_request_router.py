import json
import pytest
from unittest.mock import patch, MagicMock, Mock
from botocore.exceptions import ClientError
from src.request_router import (
    handle_devops_request,
    handle_put_secret,
    handle_deploy_lambda,
    publish_completion_event
)


class TestDevOpsRequestRouter:
    
    @patch('src.request_router.publish_completion_event')
    @patch('src.request_router.handle_put_secret')
    def test_handle_devops_request_put_secret_success(self, mock_put_secret, mock_publish):
        """Test successful putSecret request handling"""
        # Mock successful secret creation
        mock_put_secret.return_value = {
            'secretName': '/contentcraft/test/secret',
            'action': 'created',
            'arn': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:/contentcraft/test/secret-AbCdEf',
            'versionId': 'version-123'
        }
        
        event = {
            'source': 'agent.CostSentinel',
            'detail-type': 'devops.request',
            'detail': {
                'requestId': 'test-123',
                'action': 'putSecret',
                'stage': 'dev',
                'params': {
                    'name': '/contentcraft/test/secret',
                    'value': 'test-value'
                },
                'requestedBy': 'CostSentinel'
            }
        }
        
        result = handle_devops_request(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'success'
        assert body['requestId'] == 'test-123'
        assert 'latencyMs' in body
        
        # Verify completion event was published
        mock_publish.assert_called_once()
        completion_event = mock_publish.call_args[0][0]
        assert completion_event['status'] == 'success'
        assert completion_event['action'] == 'putSecret'
        assert completion_event['requestedBy'] == 'CostSentinel'
    
    @patch('src.request_router.publish_completion_event')
    def test_handle_devops_request_invalid_action(self, mock_publish):
        """Test handling of invalid action"""
        event = {
            'source': 'agent.TestAgent',
            'detail-type': 'devops.request',
            'detail': {
                'requestId': 'test-456',
                'action': 'invalidAction',
                'requestedBy': 'TestAgent'
            }
        }
        
        result = handle_devops_request(event, None)
        
        assert result['statusCode'] == 500
        body = json.loads(result['body'])
        assert body['status'] == 'error'
        assert 'Unsupported action' in body['error']
        
        # Verify error completion event was published
        mock_publish.assert_called_once()
        completion_event = mock_publish.call_args[0][0]
        assert completion_event['status'] == 'error'
    
    @patch('src.request_router.secrets_manager')
    def test_handle_put_secret_create_new(self, mock_secrets):
        """Test creating a new secret"""
        # Mock secret doesn't exist
        mock_secrets.describe_secret.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'DescribeSecret'
        )
        
        # Mock successful creation
        mock_secrets.create_secret.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret-AbCdEf',
            'VersionId': 'version-123'
        }
        
        params = {
            'name': '/contentcraft/test/secret',
            'value': 'test-value'
        }
        
        result = handle_put_secret(params, 'dev')
        
        assert result['secretName'] == '/contentcraft/test/secret'
        assert result['action'] == 'created'
        assert result['arn'] == 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret-AbCdEf'
        assert result['versionId'] == 'version-123'
        
        # Verify secret was created with proper tags
        mock_secrets.create_secret.assert_called_once()
        call_args = mock_secrets.create_secret.call_args[1]
        assert call_args['Name'] == '/contentcraft/test/secret'
        assert call_args['SecretString'] == 'test-value'
        assert any(tag['Key'] == 'createdBy' and tag['Value'] == 'DevOpsAutomation' for tag in call_args['Tags'])
    
    @patch('src.request_router.secrets_manager')
    def test_handle_put_secret_update_existing(self, mock_secrets):
        """Test updating an existing secret"""
        # Mock secret exists
        mock_secrets.describe_secret.return_value = {'Name': '/contentcraft/test/secret'}
        
        # Mock successful update
        mock_secrets.put_secret_value.return_value = {
            'ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret-AbCdEf',
            'VersionId': 'version-456'
        }
        
        params = {
            'name': '/contentcraft/test/secret',
            'value': 'updated-value'
        }
        
        result = handle_put_secret(params, 'dev')
        
        assert result['secretName'] == '/contentcraft/test/secret'
        assert result['action'] == 'updated'
        assert result['versionId'] == 'version-456'
        
        # Verify secret was updated
        mock_secrets.put_secret_value.assert_called_once_with(
            SecretId='/contentcraft/test/secret',
            SecretString='updated-value'
        )
    
    def test_handle_put_secret_missing_params(self):
        """Test putSecret with missing parameters"""
        # Missing name
        with pytest.raises(ValueError, match="putSecret requires 'name' and 'value' parameters"):
            handle_put_secret({'value': 'test'}, 'dev')
        
        # Missing value
        with pytest.raises(ValueError, match="putSecret requires 'name' and 'value' parameters"):
            handle_put_secret({'name': '/test/secret'}, 'dev')
    
    @patch('src.request_router.cloudformation')
    def test_handle_deploy_lambda_success(self, mock_cfn):
        """Test successful lambda deployment request"""
        # Mock stack exists and is in stable state
        mock_cfn.describe_stacks.return_value = {
            'Stacks': [{
                'StackStatus': 'UPDATE_COMPLETE'
            }]
        }
        
        params = {
            'stackName': 'test-stack',
            'stage': 'dev'
        }
        
        result = handle_deploy_lambda(params, 'dev')
        
        assert result['stackName'] == 'test-stack-dev'
        assert result['action'] == 'deployment_queued'
        assert result['currentStatus'] == 'UPDATE_COMPLETE'
        assert 'Phase 2 implementation' in result['note']
    
    @patch('src.request_router.cloudformation')
    def test_handle_deploy_lambda_stack_not_found(self, mock_cfn):
        """Test deployment when stack doesn't exist"""
        # Mock stack doesn't exist
        mock_cfn.describe_stacks.side_effect = ClientError(
            {'Error': {'Code': 'ValidationError', 'Message': 'Stack does not exist'}}, 
            'DescribeStacks'
        )
        
        params = {
            'stackName': 'nonexistent-stack'
        }
        
        with pytest.raises(Exception, match="Stack nonexistent-stack-dev does not exist"):
            handle_deploy_lambda(params, 'dev')
    
    @patch('src.request_router.cloudformation')
    def test_handle_deploy_lambda_in_progress(self, mock_cfn):
        """Test deployment when stack is in progress"""
        # Mock stack is in progress
        mock_cfn.describe_stacks.return_value = {
            'Stacks': [{
                'StackStatus': 'UPDATE_IN_PROGRESS'
            }]
        }
        
        params = {
            'stackName': 'test-stack'
        }
        
        with pytest.raises(Exception, match="currently in progress state: UPDATE_IN_PROGRESS"):
            handle_deploy_lambda(params, 'dev')
    
    def test_handle_deploy_lambda_missing_params(self):
        """Test deployLambda with missing parameters"""
        with pytest.raises(ValueError, match="deployLambda requires 'stackName' parameter"):
            handle_deploy_lambda({}, 'dev')
    
    @patch('src.request_router.events_client')
    def test_publish_completion_event_success(self, mock_events):
        """Test successful completion event publishing"""
        completion_data = {
            'requestId': 'test-123',
            'action': 'putSecret',
            'status': 'success',
            'latencyMs': 250
        }
        
        publish_completion_event(completion_data)
        
        mock_events.put_events.assert_called_once()
        call_args = mock_events.put_events.call_args[1]
        
        entries = call_args['Entries']
        assert len(entries) == 1
        
        entry = entries[0]
        assert entry['Source'] == 'devops.automation'
        assert entry['DetailType'] == 'devops.completed'
        
        detail = json.loads(entry['Detail'])
        assert detail['requestId'] == 'test-123'
        assert detail['action'] == 'putSecret'
        assert detail['status'] == 'success'
    
    @patch('src.request_router.events_client')
    def test_publish_completion_event_failure_handling(self, mock_events):
        """Test completion event publishing failure handling"""
        # Mock EventBridge failure
        mock_events.put_events.side_effect = Exception("EventBridge error")
        
        completion_data = {
            'requestId': 'test-123',
            'status': 'success'
        }
        
        # Should not raise exception - failure is logged but not propagated
        publish_completion_event(completion_data)
        
        mock_events.put_events.assert_called_once()


class TestEventBridgeIntegration:
    """Integration tests for EventBridge event handling"""
    
    @patch('src.request_router.handle_put_secret')
    @patch('src.request_router.publish_completion_event')
    def test_eventbridge_event_format(self, mock_publish, mock_put_secret):
        """Test that EventBridge event format is handled correctly"""
        mock_put_secret.return_value = {'secretName': 'test', 'action': 'created'}
        
        # EventBridge event format
        event = {
            'version': '0',
            'id': 'event-id',
            'detail-type': 'devops.request',
            'source': 'agent.CostSentinel',
            'account': '123456789012',
            'time': '2025-06-21T12:00:00Z',
            'region': 'us-east-1',
            'detail': {
                'requestId': 'eb-test-123',
                'action': 'putSecret',
                'stage': 'dev',
                'params': {
                    'name': '/contentcraft/eb/test',
                    'value': 'eventbridge-value'
                },
                'requestedBy': 'CostSentinel',
                'ts': '2025-06-21T12:00:00Z'
            }
        }
        
        result = handle_devops_request(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['requestId'] == 'eb-test-123'
        
        # Verify the correct parameters were passed to put_secret
        mock_put_secret.assert_called_once_with({
            'name': '/contentcraft/eb/test',
            'value': 'eventbridge-value'
        }, 'dev') 