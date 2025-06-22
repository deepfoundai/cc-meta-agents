"""
Unit tests for Lambda handler
"""
import json
import os
from unittest import mock
import pytest
from datetime import datetime, timezone

# Mock AWS services before importing handler
with mock.patch('boto3.client'), mock.patch('boto3.resource'):
    from src import handler


class TestHandler:
    """Test Lambda handler functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        os.environ['STAGE'] = 'test'
        os.environ['FAL_QUEUE_URL'] = 'https://sqs.region.amazonaws.com/123/FalJobQueue'
        os.environ['REPLICATE_QUEUE_URL'] = 'https://sqs.region.amazonaws.com/123/ReplicateJobQueue'
        
        # Reset handler module to pick up new env vars
        handler.STAGE = 'test'
        handler.FAL_QUEUE_URL = os.environ['FAL_QUEUE_URL']
        handler.REPLICATE_QUEUE_URL = os.environ['REPLICATE_QUEUE_URL']
        handler.QUEUE_URLS = {
            "fal": handler.FAL_QUEUE_URL,
            "replicate": handler.REPLICATE_QUEUE_URL
        }
    
    @mock.patch('src.handler.is_job_already_routed')
    @mock.patch('src.handler.sqs')
    @mock.patch('src.handler.events_client')
    @mock.patch('src.handler.record_routing_decision')
    def test_successful_routing_to_fal(self, mock_record, mock_events, mock_sqs, mock_already_routed):
        """Test successful routing to fal provider"""
        mock_already_routed.return_value = False
        
        event = {
            'detail': {
                'jobId': 'test-123',
                'userId': 'user-456',
                'prompt': 'corgi surfing',
                'lengthSec': 8,
                'resolution': '720p',
                'provider': 'auto'
            }
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'routed'
        assert body['provider'] == 'fal'
        assert body['model'] == 'wan-i2v'
        
        # Verify SQS message sent
        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args
        assert call_args[1]['QueueUrl'] == handler.FAL_QUEUE_URL
        assert 'MessageBody' in call_args[1]
        
        # Verify EventBridge event emitted
        mock_events.put_events.assert_called_once()
        event_entries = mock_events.put_events.call_args[1]['Entries']
        assert len(event_entries) == 1
        assert event_entries[0]['DetailType'] == 'video.job.routed'
    
    @mock.patch('src.handler.is_job_already_routed')
    def test_idempotency_check(self, mock_already_routed):
        """Test idempotency - job already routed"""
        mock_already_routed.return_value = True
        
        event = {
            'detail': {
                'jobId': 'test-123',
                'userId': 'user-456',
                'prompt': 'test',
                'lengthSec': 5,
                'resolution': '720p'
            }
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'already_processed'
    
    @mock.patch('src.handler.events_client')
    def test_job_rejection_no_route(self, mock_events):
        """Test job rejection when no route matches"""
        event = {
            'detail': {
                'jobId': 'test-123',
                'userId': 'user-456',
                'prompt': 'test',
                'lengthSec': 30,
                'resolution': '1080p',
                'provider': 'auto'
            }
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['status'] == 'rejected'
        assert body['reason'] == 'no_route'
        
        # Verify rejection event emitted
        mock_events.put_events.assert_called()
        event_entries = mock_events.put_events.call_args[1]['Entries']
        assert event_entries[0]['DetailType'] == 'video.job.rejected'
    
    @mock.patch('src.handler.cloudwatch')
    def test_heartbeat(self, mock_cloudwatch):
        """Test heartbeat functionality"""
        event = {
            'source': 'aws.events',
            'detail-type': 'Scheduled Event'
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        assert result['body'] == 'Heartbeat sent'
        
        # Verify CloudWatch metric sent
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'Agent/RoutingManager'
        assert call_args[1]['MetricData'][0]['MetricName'] == 'Heartbeat'
    
    def test_validation_error(self):
        """Test job validation failure"""
        event = {
            'detail': {
                'userId': 'user-456',
                'prompt': 'test'
                # Missing jobId
            }
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['status'] == 'rejected'
        assert 'missing_required_field:jobId' in body['reason']
    
    @mock.patch('src.handler.dynamodb')
    def test_is_job_already_routed(self, mock_dynamodb):
        """Test job routing status check"""
        # Mock table response
        mock_table = mock.Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Test job exists and is routed
        mock_table.get_item.return_value = {
            'Item': {'jobId': 'test-123', 'status': 'ROUTED'}
        }
        assert handler.is_job_already_routed('test-123') is True
        
        # Test job doesn't exist
        mock_table.get_item.return_value = {}
        assert handler.is_job_already_routed('test-456') is False
        
        # Test job exists but not routed
        mock_table.get_item.return_value = {
            'Item': {'jobId': 'test-789', 'status': 'SUBMITTED'}
        }
        assert handler.is_job_already_routed('test-789') is False
    
    @mock.patch('src.handler.is_job_already_routed')
    @mock.patch('src.handler.sqs')
    @mock.patch('src.handler.events_client')
    @mock.patch('src.handler.record_routing_decision')
    @mock.patch('src.handler.send_routing_metrics')
    def test_full_routing_flow_with_metrics(self, mock_metrics, mock_record, mock_events, mock_sqs, mock_already_routed):
        """Test complete routing flow including metrics"""
        mock_already_routed.return_value = False
        
        # Test with explicit provider
        event = {
            'detail': {
                'jobId': 'test-explicit-123',
                'userId': 'user-456',
                'prompt': 'test video',
                'lengthSec': 20,
                'resolution': '1080p',
                'provider': 'replicate'
            }
        }
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['provider'] == 'replicate'
        assert body['model'] == 'stable-video'
        
        # Verify metrics were sent
        mock_metrics.assert_called_with('replicate', True)
        
        # Verify recording was called
        mock_record.assert_called_once()
    
    def test_direct_invocation_format(self):
        """Test handler accepts direct invocation format (no 'detail' wrapper)"""
        event = {
            'jobId': 'direct-test-123',
            'userId': 'user-456',
            'prompt': 'direct test',
            'lengthSec': 5,
            'resolution': '720p',
            'provider': 'auto'
        }
        
        with mock.patch('src.handler.is_job_already_routed', return_value=False), \
             mock.patch('src.handler.sqs'), \
             mock.patch('src.handler.events_client'), \
             mock.patch('src.handler.record_routing_decision'):
            
            result = handler.lambda_handler(event, None)
            
            assert result['statusCode'] == 200
            body = json.loads(result['body'])
            assert body['provider'] == 'fal'
    
    @mock.patch('src.handler.send_routing_metrics')
    def test_error_handling_sends_metrics(self, mock_metrics):
        """Test that errors still send metrics"""
        # Invalid event that will cause an error
        event = "not a dict"
        
        result = handler.lambda_handler(event, None)
        
        assert result['statusCode'] == 500
        # Verify error metrics were sent
        mock_metrics.assert_called_with('error', False)