#!/usr/bin/env python3
"""
Smoke tests for Credit Reconciler Lambda
"""
import os
import json
import time
import boto3
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
import argparse

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


class SmokeTestRunner:
    def __init__(self, environment: str):
        self.environment = environment
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        
        # Initialize AWS clients
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.logs_client = boto3.client('logs', region_name=self.region)
        self.cloudwatch = boto3.client('cloudwatch', region_name=self.region)
        self.cf_client = boto3.client('cloudformation', region_name=self.region)
        
        # Get stack outputs
        self.stack_name = f"cc-agent-reconciler-{environment}"
        self._load_stack_outputs()
        
        # Test data
        self.test_user_id = f"smoke-test-user-{uuid.uuid4().hex[:8]}"
        self.test_job_id = f"smoke-test-job-{uuid.uuid4().hex[:8]}"
    
    def _load_stack_outputs(self):
        """Load CloudFormation stack outputs"""
        try:
            response = self.cf_client.describe_stacks(StackName=self.stack_name)
            outputs = response['Stacks'][0]['Outputs']
            
            self.function_arn = next(o['OutputValue'] for o in outputs if o['OutputKey'] == 'FunctionArn')
            self.function_name = self.function_arn.split(':')[-1]
            self.jobs_table_name = next(o['OutputValue'] for o in outputs if o['OutputKey'] == 'JobsTableName')
            self.credits_table_name = next(o['OutputValue'] for o in outputs if o['OutputKey'] == 'CreditsTableName')
            self.ledger_table_name = next(o['OutputValue'] for o in outputs if o['OutputKey'] == 'LedgerTableName')
            
            print(f"{GREEN}✅ Loaded stack outputs successfully{NC}")
        except Exception as e:
            print(f"{RED}❌ Failed to load stack outputs: {e}{NC}")
            raise
    
    def setup_test_data(self):
        """Setup test data in DynamoDB"""
        print(f"\n{YELLOW}📝 Setting up test data...{NC}")
        
        # Create test user with initial credits
        credits_table = self.dynamodb.Table(self.credits_table_name)
        credits_table.put_item(Item={
            'userId': self.test_user_id,
            'remaining': Decimal('100.00')
        })
        print(f"  Created test user: {self.test_user_id} with 100 credits")
        
        # Create test job
        jobs_table = self.dynamodb.Table(self.jobs_table_name)
        jobs_table.put_item(Item={
            'jobId': self.test_job_id,
            'userId': self.test_user_id,
            'status': 'processing',
            'seconds': 10,
            'model': 'default',
            'reconciled': False
        })
        print(f"  Created test job: {self.test_job_id}")
    
    def cleanup_test_data(self):
        """Cleanup test data from DynamoDB"""
        print(f"\n{YELLOW}🧹 Cleaning up test data...{NC}")
        
        try:
            # Delete test user
            credits_table = self.dynamodb.Table(self.credits_table_name)
            credits_table.delete_item(Key={'userId': self.test_user_id})
            
            # Delete test job
            jobs_table = self.dynamodb.Table(self.jobs_table_name)
            jobs_table.delete_item(Key={'jobId': self.test_job_id})
            
            # Delete ledger entries
            ledger_table = self.dynamodb.Table(self.ledger_table_name)
            response = ledger_table.query(
                IndexName='UserIdIndex',
                KeyConditionExpression='userId = :uid',
                ExpressionAttributeValues={':uid': self.test_user_id}
            )
            for item in response.get('Items', []):
                ledger_table.delete_item(Key={'ledgerId': item['ledgerId']})
            
            print(f"{GREEN}  ✅ Cleanup completed{NC}")
        except Exception as e:
            print(f"{YELLOW}  ⚠️  Cleanup warning: {e}{NC}")
    
    def invoke_lambda(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke Lambda function and return response"""
        response = self.lambda_client.invoke(
            FunctionName=self.function_name,
            InvocationType='RequestResponse',
            LogType='Tail',
            Payload=json.dumps(event)
        )
        
        payload = json.loads(response['Payload'].read())
        return payload
    
    def test_video_rendered(self) -> bool:
        """Test video.rendered event processing"""
        print(f"\n{BLUE}🎬 Testing video.rendered event...{NC}")
        
        event = {
            'source': 'aws.events',
            'detail-type': 'video.rendered',
            'detail': {
                'jobId': self.test_job_id,
                'userId': self.test_user_id,
                'seconds': 10,
                'model': 'default',
                'result_url': 's3://test-bucket/result.mp4'
            }
        }
        
        try:
            # Invoke Lambda
            response = self.invoke_lambda(event)
            
            # Check response
            if response.get('statusCode') != 200:
                print(f"{RED}  ❌ Unexpected status code: {response.get('statusCode')}{NC}")
                return False
            
            # Verify credit deduction
            time.sleep(1)  # Wait for DynamoDB consistency
            credits_table = self.dynamodb.Table(self.credits_table_name)
            credits = credits_table.get_item(Key={'userId': self.test_user_id})['Item']
            
            expected_credits = Decimal('99.00')  # 100 - (10 seconds * 0.10)
            actual_credits = credits['remaining']
            
            if actual_credits == expected_credits:
                print(f"{GREEN}  ✅ Credits correctly debited: {actual_credits}{NC}")
            else:
                print(f"{RED}  ❌ Credit mismatch. Expected: {expected_credits}, Actual: {actual_credits}{NC}")
                return False
            
            # Verify ledger entry
            ledger_table = self.dynamodb.Table(self.ledger_table_name)
            ledger_entries = ledger_table.query(
                IndexName='JobIdIndex',
                KeyConditionExpression='jobId = :jid',
                ExpressionAttributeValues={':jid': self.test_job_id}
            )
            
            if ledger_entries['Count'] > 0:
                entry = ledger_entries['Items'][0]
                print(f"{GREEN}  ✅ Ledger entry created: {entry['type']} - ${entry['amount']}{NC}")
            else:
                print(f"{RED}  ❌ No ledger entry found{NC}")
                return False
            
            return True
            
        except Exception as e:
            print(f"{RED}  ❌ Error: {e}{NC}")
            return False
    
    def test_video_failed(self) -> bool:
        """Test video.failed event processing"""
        print(f"\n{BLUE}🚫 Testing video.failed event...{NC}")
        
        # Create a new failed job
        failed_job_id = f"smoke-test-failed-{uuid.uuid4().hex[:8]}"
        
        # First, create a debit for this job
        print(f"  Setting up failed job scenario...")
        debit_event = {
            'source': 'aws.events',
            'detail-type': 'video.rendered',
            'detail': {
                'jobId': failed_job_id,
                'userId': self.test_user_id,
                'seconds': 20,
                'model': 'default'
            }
        }
        self.invoke_lambda(debit_event)
        time.sleep(1)
        
        # Now process the failure
        event = {
            'source': 'aws.events',
            'detail-type': 'video.failed',
            'detail': {
                'jobId': failed_job_id,
                'userId': self.test_user_id
            }
        }
        
        try:
            # Get credits before refund
            credits_table = self.dynamodb.Table(self.credits_table_name)
            credits_before = credits_table.get_item(Key={'userId': self.test_user_id})['Item']['remaining']
            
            # Invoke Lambda
            response = self.invoke_lambda(event)
            
            # Check response
            if response.get('statusCode') != 200:
                print(f"{RED}  ❌ Unexpected status code: {response.get('statusCode')}{NC}")
                return False
            
            # Verify credit refund
            time.sleep(1)
            credits_after = credits_table.get_item(Key={'userId': self.test_user_id})['Item']['remaining']
            refund_amount = Decimal('2.00')  # 20 seconds * 0.10
            
            if credits_after == credits_before + refund_amount:
                print(f"{GREEN}  ✅ Credits correctly refunded: +${refund_amount}{NC}")
            else:
                print(f"{RED}  ❌ Refund mismatch. Expected: {credits_before + refund_amount}, Actual: {credits_after}{NC}")
                return False
            
            # Verify refund ledger entry
            ledger_table = self.dynamodb.Table(self.ledger_table_name)
            ledger_entries = ledger_table.query(
                IndexName='JobIdIndex',
                KeyConditionExpression='jobId = :jid',
                ExpressionAttributeValues={':jid': failed_job_id}
            )
            
            credit_entries = [e for e in ledger_entries['Items'] if e['type'] == 'credit']
            if credit_entries:
                print(f"{GREEN}  ✅ Refund ledger entry created{NC}")
            else:
                print(f"{RED}  ❌ No refund ledger entry found{NC}")
                return False
            
            return True
            
        except Exception as e:
            print(f"{RED}  ❌ Error: {e}{NC}")
            return False
    
    def test_timer_scan(self) -> bool:
        """Test timer scan functionality"""
        print(f"\n{BLUE}⏰ Testing timer scan...{NC}")
        
        # Create unreconciled job
        unreconciled_job_id = f"smoke-test-unrec-{uuid.uuid4().hex[:8]}"
        jobs_table = self.dynamodb.Table(self.jobs_table_name)
        jobs_table.put_item(Item={
            'jobId': unreconciled_job_id,
            'userId': self.test_user_id,
            'status': 'completed',
            'seconds': 5,
            'model': 'default',
            'reconciled': False
        })
        
        event = {
            'source': 'aws.events',
            'detail-type': 'Scheduled Event'
        }
        
        try:
            # Invoke Lambda
            response = self.invoke_lambda(event)
            
            # Check response
            if response.get('statusCode') != 200:
                print(f"{RED}  ❌ Unexpected status code: {response.get('statusCode')}{NC}")
                return False
            
            body = json.loads(response.get('body', '{}'))
            if body.get('processed', 0) > 0:
                print(f"{GREEN}  ✅ Timer scan processed {body.get('processed')} jobs{NC}")
            else:
                print(f"{YELLOW}  ⚠️  No jobs processed in timer scan{NC}")
            
            # Cleanup
            jobs_table.delete_item(Key={'jobId': unreconciled_job_id})
            
            return True
            
        except Exception as e:
            print(f"{RED}  ❌ Error: {e}{NC}")
            return False
    
    def test_idempotency(self) -> bool:
        """Test idempotent processing"""
        print(f"\n{BLUE}🔄 Testing idempotency...{NC}")
        
        idempotent_job_id = f"smoke-test-idem-{uuid.uuid4().hex[:8]}"
        event = {
            'source': 'aws.events',
            'detail-type': 'video.rendered',
            'detail': {
                'jobId': idempotent_job_id,
                'userId': self.test_user_id,
                'seconds': 15,
                'model': 'default'
            }
        }
        
        try:
            # First invocation
            response1 = self.invoke_lambda(event)
            time.sleep(1)
            
            # Second invocation (should be idempotent)
            response2 = self.invoke_lambda(event)
            
            body2 = json.loads(response2.get('body', '{}'))
            if 'Already processed' in body2.get('message', ''):
                print(f"{GREEN}  ✅ Idempotency check passed{NC}")
                return True
            else:
                print(f"{RED}  ❌ Idempotency check failed{NC}")
                return False
            
        except Exception as e:
            print(f"{RED}  ❌ Error: {e}{NC}")
            return False
    
    def check_logs(self):
        """Check CloudWatch logs for errors"""
        print(f"\n{BLUE}📋 Checking CloudWatch logs...{NC}")
        
        log_group = f"/aws/lambda/{self.function_name}"
        
        try:
            # Get latest log streams
            response = self.logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=1
            )
            
            if not response['logStreams']:
                print(f"{YELLOW}  ⚠️  No log streams found{NC}")
                return
            
            latest_stream = response['logStreams'][0]['logStreamName']
            
            # Check for errors in last 5 minutes
            response = self.logs_client.filter_log_events(
                logGroupName=log_group,
                logStreamNames=[latest_stream],
                startTime=int((time.time() - 300) * 1000),
                filterPattern='{ $.level = "error" }'
            )
            
            if response['events']:
                print(f"{RED}  ❌ Found {len(response['events'])} error(s) in logs{NC}")
                for event in response['events'][:3]:  # Show first 3 errors
                    print(f"    {event['message']}")
            else:
                print(f"{GREEN}  ✅ No errors found in recent logs{NC}")
                
        except Exception as e:
            print(f"{YELLOW}  ⚠️  Could not check logs: {e}{NC}")
    
    def check_metrics(self):
        """Check CloudWatch metrics"""
        print(f"\n{BLUE}📊 Checking CloudWatch metrics...{NC}")
        
        try:
            # Check Lambda errors
            response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Errors',
                Dimensions=[
                    {'Name': 'FunctionName', 'Value': self.function_name}
                ],
                StartTime=datetime.utcnow().replace(hour=0, minute=0, second=0),
                EndTime=datetime.utcnow(),
                Period=3600,
                Statistics=['Sum']
            )
            
            total_errors = sum(dp['Sum'] for dp in response['Datapoints'])
            if total_errors > 0:
                print(f"{YELLOW}  ⚠️  Found {int(total_errors)} Lambda errors today{NC}")
            else:
                print(f"{GREEN}  ✅ No Lambda errors today{NC}")
            
            # Check custom metrics
            response = self.cloudwatch.get_metric_statistics(
                Namespace='Reconciler',
                MetricName='Adjustments',
                StartTime=datetime.utcnow().replace(hour=0, minute=0, second=0),
                EndTime=datetime.utcnow(),
                Period=3600,
                Statistics=['Sum']
            )
            
            total_adjustments = sum(dp['Sum'] for dp in response['Datapoints'])
            print(f"{BLUE}  ℹ️  Total adjustments today: {int(total_adjustments)}{NC}")
            
        except Exception as e:
            print(f"{YELLOW}  ⚠️  Could not check metrics: {e}{NC}")
    
    def run_all_tests(self) -> bool:
        """Run all smoke tests"""
        print(f"\n{GREEN}🚀 Running smoke tests for {self.stack_name}{NC}")
        print(f"Function: {self.function_name}")
        
        # Setup
        self.setup_test_data()
        
        # Run tests
        tests = [
            self.test_video_rendered,
            self.test_video_failed,
            self.test_timer_scan,
            self.test_idempotency
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            if test():
                passed += 1
            else:
                failed += 1
        
        # Check logs and metrics
        self.check_logs()
        self.check_metrics()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Summary
        print(f"\n{GREEN}{'='*50}{NC}")
        print(f"{GREEN}✅ PASSED: {passed}{NC}")
        if failed > 0:
            print(f"{RED}❌ FAILED: {failed}{NC}")
        else:
            print(f"{GREEN}🎉 All tests passed!{NC}")
        print(f"{GREEN}{'='*50}{NC}")
        
        return failed == 0


def main():
    parser = argparse.ArgumentParser(description='Run smoke tests for Credit Reconciler')
    parser.add_argument('--env', default='dev', choices=['dev', 'staging', 'prod'],
                        help='Environment to test (default: dev)')
    args = parser.parse_args()
    
    runner = SmokeTestRunner(args.env)
    success = runner.run_all_tests()
    
    exit(0 if success else 1)


if __name__ == '__main__':
    main()