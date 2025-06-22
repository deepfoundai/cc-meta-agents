#!/usr/bin/env python3
"""
Smoke tests for CC Agent DevOps Automation
"""
import sys
import json
import argparse
import boto3
from datetime import datetime


def test_devops_function(function_name: str, stage: str):
    """Test the DevOps automation function"""
    print(f"\n🧪 Testing {function_name}...")
    
    lambda_client = boto3.client('lambda')
    
    # Test health check
    print("  - Testing health check...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps({'task_type': 'health_check'})
    )
    
    result = json.loads(response['Payload'].read())
    if result.get('statusCode') == 200:
        print("  ✅ Health check passed")
    else:
        print(f"  ❌ Health check failed: {result}")
        return False
    
    # Test GitHub repo check
    print("  - Testing GitHub repo check...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps({
            'task_type': 'github_repo_check',
            'repository': 'cc-agent-doc-registry'
        })
    )
    
    result = json.loads(response['Payload'].read())
    if result.get('statusCode') == 200:
        body = json.loads(result['body'])
        print(f"  ✅ GitHub check completed. Issues found: {len(body.get('issues_found', []))}")
        if body.get('issues_found'):
            for issue in body['issues_found']:
                print(f"     - {issue}")
    else:
        print(f"  ❌ GitHub check failed: {result}")
        return False
    
    return True


def test_mrr_reporter(function_name: str, stage: str):
    """Test the MRR reporter function"""
    print(f"\n🧪 Testing {function_name}...")
    
    lambda_client = boto3.client('lambda')
    
    print("  - Invoking MRR calculation...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps({})
    )
    
    result = json.loads(response['Payload'].read())
    if result.get('statusCode') == 200:
        body = json.loads(result['body'])
        print(f"  ✅ MRR calculation completed. MRR: ${body.get('mrrUSD', 0)}")
    else:
        print(f"  ❌ MRR calculation failed: {result}")
        return False
    
    # Verify DynamoDB write
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(f'BillingMetrics-{stage}')
    
    try:
        response = table.get_item(Key={'PK': 'mrr', 'SK': 'latest'})
        if 'Item' in response:
            print(f"  ✅ DynamoDB item verified. MRR: ${response['Item']['mrrUSD']}")
        else:
            print("  ⚠️  No MRR data in DynamoDB yet")
    except Exception as e:
        print(f"  ⚠️  Could not verify DynamoDB: {e}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='Run smoke tests for DevOps Automation')
    parser.add_argument('--stage', default='dev', choices=['dev', 'prod'],
                        help='Deployment stage')
    args = parser.parse_args()
    
    print(f"🚀 Running smoke tests for stage: {args.stage}")
    
    # Test DevOps automation function
    devops_function = f'cc-agent-devops-automation-{args.stage}'
    devops_success = test_devops_function(devops_function, args.stage)
    
    # Test MRR reporter function
    mrr_function = f'StripeMrrReporterFn-{args.stage}'
    mrr_success = test_mrr_reporter(mrr_function, args.stage)
    
    # Summary
    print("\n📊 Test Summary:")
    print(f"  - DevOps Automation: {'✅ PASSED' if devops_success else '❌ FAILED'}")
    print(f"  - MRR Reporter: {'✅ PASSED' if mrr_success else '❌ FAILED'}")
    
    if devops_success and mrr_success:
        print("\n✅ All smoke tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())