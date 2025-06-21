import pytest
import json
import os
from decimal import Decimal
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

# Set environment variables before importing handler
os.environ['JOBS_TABLE'] = 'test-jobs'
os.environ['CREDITS_TABLE'] = 'test-credits'
os.environ['LEDGER_TABLE'] = 'test-ledger'
os.environ['OPENAI_API_KEY'] = 'test-key'
os.environ['LLM_MODEL'] = 'gpt-4.1'

from src.handler import (
    lambda_handler, handle_video_rendered, handle_video_failed,
    handle_timer_scan, get_model_price, is_anomaly, invoke_llm
)


@pytest.fixture
def dynamodb_tables():
    """Create test DynamoDB tables using moto."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create Jobs table
        jobs_table = dynamodb.create_table(
            TableName='test-jobs',
            KeySchema=[{'AttributeName': 'jobId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'jobId', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create Credits table
        credits_table = dynamodb.create_table(
            TableName='test-credits',
            KeySchema=[{'AttributeName': 'userId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'userId', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create Ledger table with GSI
        ledger_table = dynamodb.create_table(
            TableName='test-ledger',
            KeySchema=[{'AttributeName': 'ledgerId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'ledgerId', 'AttributeType': 'S'},
                {'AttributeName': 'jobId', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'JobIdIndex',
                'KeySchema': [{'AttributeName': 'jobId', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'}
            }],
            BillingMode='PAY_PER_REQUEST'
        )
        
        yield {
            'jobs': jobs_table,
            'credits': credits_table,
            'ledger': ledger_table
        }


@pytest.fixture
def ssm_parameters():
    """Create test SSM parameters."""
    with mock_aws():
        ssm = boto3.client('ssm', region_name='us-east-1')
        ssm.put_parameter(
            Name='/fertilia/pricing/default',
            Value='0.10',
            Type='String'
        )
        ssm.put_parameter(
            Name='/fertilia/pricing/premium',
            Value='0.25',
            Type='String'
        )
        yield ssm


class TestLambdaHandler:
    """Test the main Lambda handler routing."""
    
    def test_video_rendered_event(self, dynamodb_tables, ssm_parameters):
        """Test handling of video.rendered events."""
        # Add initial credits
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('100.00')
        })
        
        event = {
            'source': 'aws.events',
            'detail-type': 'video.rendered',
            'detail': {
                'jobId': 'job123',
                'userId': 'user123',
                'seconds': 10,
                'model': 'default'
            }
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        
        # Check ledger entry created
        ledger_items = dynamodb_tables['ledger'].scan()['Items']
        assert len(ledger_items) == 1
        assert ledger_items[0]['type'] == 'debit'
        assert ledger_items[0]['amount'] == Decimal('1.00')  # 10 seconds * 0.10
        
        # Check credits updated
        credits = dynamodb_tables['credits'].get_item(Key={'userId': 'user123'})['Item']
        assert credits['remaining'] == Decimal('99.00')
    
    def test_video_failed_event(self, dynamodb_tables, ssm_parameters):
        """Test handling of video.failed events."""
        # Setup: create initial debit
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('90.00')
        })
        
        dynamodb_tables['ledger'].put_item(Item={
            'ledgerId': 'user123#2024-01-01#job123',
            'userId': 'user123',
            'type': 'debit',
            'amount': Decimal('10.00'),
            'jobId': 'job123',
            'reference': 'job123'
        })
        
        event = {
            'source': 'aws.events',
            'detail-type': 'video.failed',
            'detail': {
                'jobId': 'job123',
                'userId': 'user123'
            }
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        
        # Check refund entry created
        ledger_items = dynamodb_tables['ledger'].scan()['Items']
        refund_items = [item for item in ledger_items if item['type'] == 'credit']
        assert len(refund_items) == 1
        assert refund_items[0]['amount'] == Decimal('10.00')
        
        # Check credits restored
        credits = dynamodb_tables['credits'].get_item(Key={'userId': 'user123'})['Item']
        assert credits['remaining'] == Decimal('100.00')
    
    def test_scheduled_timer_event(self, dynamodb_tables, ssm_parameters):
        """Test scheduled timer scan event."""
        event = {
            'source': 'aws.events',
            'detail-type': 'Scheduled Event'
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'Timer scan completed' in body['message']


class TestVideoRenderedHandler:
    """Test video.rendered event processing."""
    
    def test_successful_debit(self, dynamodb_tables, ssm_parameters):
        """Test successful credit debit for rendered video."""
        # Setup
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('100.00')
        })
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123',
            'seconds': 30,
            'model': 'premium'
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = handle_video_rendered(detail)
        
        assert response['statusCode'] == 200
        
        # Verify debit amount (30 seconds * 0.25 = 7.50)
        ledger_items = dynamodb_tables['ledger'].scan()['Items']
        assert len(ledger_items) == 1
        assert ledger_items[0]['amount'] == Decimal('7.50')
    
    def test_idempotent_debit(self, dynamodb_tables, ssm_parameters):
        """Test that duplicate debits are prevented."""
        # Setup existing debit
        dynamodb_tables['ledger'].put_item(Item={
            'ledgerId': 'user123#2024-01-01#job123',
            'userId': 'user123',
            'type': 'debit',
            'amount': Decimal('5.00'),
            'jobId': 'job123',
            'reference': 'job123'
        })
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123',
            'seconds': 20,
            'model': 'default'
        }
        
        response = handle_video_rendered(detail)
        
        assert response['statusCode'] == 200
        assert 'Already processed' in response['body']
    
    @patch('src.handler.invoke_llm')
    def test_anomaly_detection(self, mock_llm, dynamodb_tables, ssm_parameters):
        """Test anomaly detection for high-cost jobs."""
        mock_llm.return_value = "Unusually long video generation detected."
        
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('1000.00')
        })
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123',
            'seconds': 600,  # 10 minutes - triggers anomaly
            'model': 'default'
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = handle_video_rendered(detail)
        
        assert response['statusCode'] == 200
        
        # Check anomaly was recorded
        ledger_items = dynamodb_tables['ledger'].scan()['Items']
        assert 'anomaly' in ledger_items[0]
        assert mock_llm.called


class TestVideoFailedHandler:
    """Test video.failed event processing."""
    
    def test_successful_refund(self, dynamodb_tables):
        """Test successful credit refund for failed video."""
        # Setup
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('80.00')
        })
        
        dynamodb_tables['ledger'].put_item(Item={
            'ledgerId': 'user123#2024-01-01#job123',
            'userId': 'user123',
            'type': 'debit',
            'amount': Decimal('20.00'),
            'jobId': 'job123',
            'reference': 'job123'
        })
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123'
        }
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = handle_video_failed(detail)
        
        assert response['statusCode'] == 200
        
        # Verify refund
        credits = dynamodb_tables['credits'].get_item(Key={'userId': 'user123'})['Item']
        assert credits['remaining'] == Decimal('100.00')
    
    def test_no_debit_to_refund(self, dynamodb_tables):
        """Test handling when no debit exists to refund."""
        detail = {
            'jobId': 'job999',
            'userId': 'user123'
        }
        
        response = handle_video_failed(detail)
        
        assert response['statusCode'] == 200
        assert 'No debit to refund' in response['body']
    
    def test_idempotent_refund(self, dynamodb_tables):
        """Test that duplicate refunds are prevented."""
        # Setup existing refund
        dynamodb_tables['ledger'].put_item(Item={
            'ledgerId': 'user123#2024-01-01#job123',
            'userId': 'user123',
            'type': 'debit',
            'amount': Decimal('10.00'),
            'jobId': 'job123',
            'reference': 'job123'
        })
        
        dynamodb_tables['ledger'].put_item(Item={
            'ledgerId': 'user123#2024-01-02#job123#refund',
            'userId': 'user123',
            'type': 'credit',
            'amount': Decimal('10.00'),
            'jobId': 'job123',
            'reference': 'job123'
        })
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123'
        }
        
        response = handle_video_failed(detail)
        
        assert response['statusCode'] == 200
        assert 'Already refunded' in response['body']


class TestTimerScan:
    """Test timer scan functionality."""
    
    def test_scan_unreconciled_jobs(self, dynamodb_tables, ssm_parameters):
        """Test scanning and processing unreconciled jobs."""
        # Setup unreconciled jobs
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('100.00')
        })
        
        dynamodb_tables['jobs'].put_item(Item={
            'jobId': 'job123',
            'userId': 'user123',
            'status': 'completed',
            'seconds': 15,
            'model': 'default',
            'reconciled': False
        })
        
        dynamodb_tables['jobs'].put_item(Item={
            'jobId': 'job124',
            'userId': 'user123',
            'status': 'failed',
            'reconciled': False
        })
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = handle_timer_scan()
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['processed'] >= 1
    
    def test_scan_with_pagination(self, dynamodb_tables, ssm_parameters):
        """Test timer scan handles pagination correctly."""
        # Create many unreconciled jobs
        dynamodb_tables['credits'].put_item(Item={
            'userId': 'user123',
            'remaining': Decimal('1000.00')
        })
        
        for i in range(30):
            dynamodb_tables['jobs'].put_item(Item={
                'jobId': f'job{i:03d}',
                'userId': 'user123',
                'status': 'completed',
                'seconds': 5,
                'model': 'default',
                'reconciled': False
            })
        
        with patch('src.handler.cloudwatch') as mock_cw:
            response = handle_timer_scan()
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['processed'] == 30


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_get_model_price(self, ssm_parameters):
        """Test retrieving model prices from SSM."""
        price = get_model_price('premium')
        assert price == 0.25
        
        # Test default price for unknown model
        price = get_model_price('unknown-model')
        assert price == 0.10
    
    def test_is_anomaly(self):
        """Test anomaly detection logic."""
        # High cost anomaly
        assert is_anomaly(Decimal('60'), 100, {})
        
        # Long duration anomaly
        assert is_anomaly(Decimal('10'), 400, {})
        
        # Missing result_url anomaly
        assert is_anomaly(Decimal('10'), 50, {'result_url': None})
        
        # Normal job
        assert not is_anomaly(Decimal('10'), 50, {'result_url': 's3://bucket/result.mp4'})
    
    @patch('src.handler.client')
    def test_invoke_llm(self, mock_client):
        """Test LLM invocation for anomaly explanation."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test anomaly explanation."))]
        mock_client.chat.completions.create.return_value = mock_response
        
        result = invoke_llm("Explain anomaly")
        assert result == "Test anomaly explanation."
        
        # Test with no API key
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            result = invoke_llm("Explain anomaly")
            assert result is None


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_missing_required_fields(self, dynamodb_tables):
        """Test handling of events with missing required fields."""
        detail = {
            'jobId': 'job123',
            # Missing userId
            'seconds': 10
        }
        
        response = handle_video_rendered(detail)
        assert response['statusCode'] == 400
        assert 'Missing required fields' in response['body']
    
    @patch('src.handler.dynamodb')
    def test_dynamodb_error_handling(self, mock_dynamodb):
        """Test handling of DynamoDB errors."""
        mock_table = MagicMock()
        mock_table.query.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'Query'
        )
        mock_dynamodb.Table.return_value = mock_table
        
        detail = {
            'jobId': 'job123',
            'userId': 'user123',
            'seconds': 10,
            'model': 'default'
        }
        
        with pytest.raises(ClientError):
            handle_video_rendered(detail)