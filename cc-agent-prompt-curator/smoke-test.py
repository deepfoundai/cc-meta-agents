#!/usr/bin/env python3

import boto3
import json
import sys
import time
from datetime import datetime

def smoke_test():
    """
    Smoke test for cc-agent-prompt-curator
    """
    print("🚀 Starting smoke test for cc-agent-prompt-curator...")
    
    # AWS clients
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    events_client = boto3.client('events', region_name='us-east-1')
    
    # Get stack outputs
    cf_client = boto3.client('cloudformation', region_name='us-east-1')
    try:
        stack = cf_client.describe_stacks(StackName='cc-agent-prompt-curator-dev')
        outputs = {o['OutputKey']: o['OutputValue'] for o in stack['Stacks'][0]['Outputs']}
        
        function_arn = outputs['PromptCuratorFunctionArn']
        bucket_name = outputs['PromptTemplatesBucketName']
        table_name = outputs['PromptTemplatesTableName']
        
        print(f"✅ Stack found with outputs:")
        print(f"   Function: {function_arn}")
        print(f"   Bucket: {bucket_name}")
        print(f"   Table: {table_name}")
        
    except Exception as e:
        print(f"❌ Failed to get stack outputs: {e}")
        return False
    
    # Test 1: Invoke Lambda function
    print("\n🧪 Test 1: Invoking Lambda function...")
    try:
        function_name = function_arn.split(':')[-1]
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({})
        )
        
        if response['StatusCode'] == 200:
            payload = json.loads(response['Payload'].read())
            print(f"✅ Lambda invocation successful: {payload}")
        else:
            print(f"❌ Lambda invocation failed with status: {response['StatusCode']}")
            return False
            
    except Exception as e:
        print(f"❌ Lambda invocation error: {e}")
        return False
    
    # Test 2: Check S3 files
    print("\n🧪 Test 2: Checking S3 files...")
    try:
        objects = s3_client.list_objects_v2(Bucket=bucket_name)
        if 'Contents' in objects:
            files = [obj['Key'] for obj in objects['Contents']]
            print(f"✅ S3 files found: {files}")
            
            # Check latest.json content
            if 'latest.json' in files:
                obj = s3_client.get_object(Bucket=bucket_name, Key='latest.json')
                content = json.loads(obj['Body'].read())
                print(f"✅ latest.json content: {content}")
            else:
                print("❌ latest.json not found")
                return False
        else:
            print("❌ No S3 files found")
            return False
            
    except Exception as e:
        print(f"❌ S3 check error: {e}")
        return False
    
    # Test 3: Check DynamoDB table
    print("\n🧪 Test 3: Checking DynamoDB table...")
    try:
        table = dynamodb.Table(table_name)
        response = table.scan(Limit=1)
        print(f"✅ DynamoDB table accessible, item count: {response['Count']}")
        
    except Exception as e:
        print(f"❌ DynamoDB check error: {e}")
        return False
    
    # Test 4: Check EventBridge rule
    print("\n🧪 Test 4: Checking EventBridge rule...")
    try:
        rules = events_client.list_rules()
        curator_rules = [r for r in rules['Rules'] if 'PromptCurator' in r['Name']]
        
        if curator_rules:
            rule = curator_rules[0]
            print(f"✅ EventBridge rule found: {rule['Name']}")
            print(f"   Schedule: {rule.get('ScheduleExpression', 'N/A')}")
            print(f"   State: {rule['State']}")
        else:
            print("❌ EventBridge rule not found")
            return False
            
    except Exception as e:
        print(f"❌ EventBridge check error: {e}")
        return False
    
    print("\n🎉 All smoke tests passed! The cc-agent-prompt-curator is deployed and working correctly.")
    return True

if __name__ == "__main__":
    success = smoke_test()
    sys.exit(0 if success else 1)
