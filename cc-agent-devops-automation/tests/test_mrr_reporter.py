import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime, timezone
from src.mrr_reporter import lambda_handler, calculate_mrr


class TestMrrReporter:
    
    @patch('boto3.client')
    @patch('boto3.resource')
    @patch('stripe.BalanceTransaction')
    def test_lambda_handler_success(self, mock_stripe, mock_dynamodb_resource, mock_boto_client):
        """Test successful MRR calculation and reporting"""
        # Mock Secrets Manager
        secrets_client = MagicMock()
        secrets_client.get_secret_value.return_value = {
            'SecretString': json.dumps({'api_key': 'sk_test_123'})
        }
        
        # Mock EventBridge
        events_client = MagicMock()
        
        mock_boto_client.side_effect = lambda service: {
            'secretsmanager': secrets_client,
            'events': events_client
        }.get(service)
        
        # Mock DynamoDB
        table = MagicMock()
        mock_dynamodb_resource.return_value.Table.return_value = table
        
        # Mock Stripe charges and refunds
        mock_charges = [
            MagicMock(amount=10000, currency='usd'),  # $100
            MagicMock(amount=5000, currency='usd'),   # $50
        ]
        mock_refunds = [
            MagicMock(amount=-1000, currency='usd'),  # $10 refund
        ]
        
        mock_stripe.list.return_value.auto_paging_iter.side_effect = [
            mock_charges, mock_refunds
        ]
        
        # Execute handler
        response = lambda_handler({}, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'success'
        assert body['mrrUSD'] == 140.0  # $150 - $10
        
        # Verify DynamoDB write
        table.put_item.assert_called_once()
        put_args = table.put_item.call_args[1]['Item']
        assert put_args['PK'] == 'mrr'
        assert put_args['SK'] == 'latest'
        assert put_args['mrrUSD'] == Decimal('140.0')
        
        # Verify EventBridge event
        events_client.put_events.assert_called_once()
        event_entry = events_client.put_events.call_args[1]['Entries'][0]
        assert event_entry['Source'] == 'billing.system'
        assert event_entry['DetailType'] == 'billing.mrr.reported'
        detail = json.loads(event_entry['Detail'])
        assert detail['mrrUSD'] == 140.0
    
    @patch('stripe.BalanceTransaction')
    def test_calculate_mrr(self, mock_stripe):
        """Test MRR calculation logic"""
        # Mock Stripe transactions
        mock_charges = [
            MagicMock(amount=20000, currency='usd'),  # $200
            MagicMock(amount=15000, currency='usd'),  # $150
            MagicMock(amount=5000, currency='eur'),   # Skip non-USD
        ]
        mock_refunds = [
            MagicMock(amount=-5000, currency='usd'),  # $50 refund
            MagicMock(amount=-2000, currency='eur'),  # Skip non-USD
        ]
        
        mock_stripe.list.return_value.auto_paging_iter.side_effect = [
            mock_charges, mock_refunds
        ]
        
        # Calculate MRR
        mrr = calculate_mrr()
        
        # Verify calculation: ($200 + $150) - $50 = $300
        assert mrr == 300.0
        
        # Verify Stripe API calls
        assert mock_stripe.list.call_count == 2
        charges_call = mock_stripe.list.call_args_list[0]
        assert charges_call[1]['type'] == 'charge'
        assert 'created' in charges_call[1]
        
        refunds_call = mock_stripe.list.call_args_list[1]
        assert refunds_call[1]['type'] == 'refund'
    
    @patch('boto3.client')
    def test_lambda_handler_error_handling(self, mock_boto_client):
        """Test error handling in lambda handler"""
        # Mock Secrets Manager to raise error
        secrets_client = MagicMock()
        secrets_client.get_secret_value.side_effect = Exception("Secret not found")
        
        mock_boto_client.return_value = secrets_client
        
        # Execute handler
        response = lambda_handler({}, None)
        
        # Verify error response
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['status'] == 'failed'
        assert 'Secret not found' in body['error']
    
    @patch('stripe.BalanceTransaction')
    def test_calculate_mrr_no_transactions(self, mock_stripe):
        """Test MRR calculation with no transactions"""
        # Mock empty transaction lists
        mock_stripe.list.return_value.auto_paging_iter.side_effect = [[], []]
        
        # Calculate MRR
        mrr = calculate_mrr()
        
        # Should return 0 for no transactions
        assert mrr == 0.0