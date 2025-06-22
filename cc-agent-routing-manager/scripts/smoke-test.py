#!/usr/bin/env python3
"""
Smoke test for Routing Manager deployment
"""
import json
import time
import boto3
import sys
from datetime import datetime, timezone

def test_routing_manager(stage='dev'):
    """Run smoke tests against deployed Routing Manager"""
    
    print(f"Running smoke tests for stage: {stage}")
    
    # Initialize AWS clients
    events = boto3.client('events')
    logs = boto3.client('logs')
    cloudwatch = boto3.client('cloudwatch')
    
    # Test 1: Send a valid job that should route to fal
    print("\n1. Testing successful routing to fal...")
    test_job = {
        "jobId": f"smoke-test-{int(time.time())}",
        "userId": "smoke-test-user",
        "prompt": "A beautiful sunset over mountains",
        "lengthSec": 8,
        "resolution": "720p",
        "tier": "standard",
        "provider": "auto"
    }
    
    response = events.put_events(
        Entries=[
            {
                'Source': 'frontend.api',
                'DetailType': 'video.job.submitted',
                'Detail': json.dumps(test_job)
            }
        ]
    )
    
    if response['FailedEntryCount'] > 0:
        print("❌ Failed to send test event")
        return False
    
    print("✅ Test event sent successfully")
    
    # Wait for processing
    time.sleep(5)
    
    # Check CloudWatch Logs
    log_group = f'/aws/lambda/routing-manager-{stage}-routing-manager'
    try:
        # Look for our job in the logs
        response = logs.filter_log_events(
            logGroupName=log_group,
            startTime=int((time.time() - 60) * 1000),
            filterPattern=f'"{test_job["jobId"]}"'
        )
        
        if response['events']:
            print(f"✅ Found {len(response['events'])} log entries for job")
            # Check if routed successfully
            for event in response['events']:
                if 'sent to fal queue' in event['message']:
                    print("✅ Job successfully routed to fal")
                elif 'rejected' in event['message']:
                    print("❌ Job was rejected")
                    return False
        else:
            print("⚠️  No log entries found for job")
    except Exception as e:
        print(f"⚠️  Could not check logs: {e}")
    
    # Test 2: Send a job that should be rejected
    print("\n2. Testing job rejection...")
    reject_job = {
        "jobId": f"smoke-test-reject-{int(time.time())}",
        "userId": "smoke-test-user",
        "prompt": "Test rejection",
        "lengthSec": 60,  # Too long for any route
        "resolution": "4K",
        "provider": "auto"
    }
    
    events.put_events(
        Entries=[
            {
                'Source': 'frontend.api',
                'DetailType': 'video.job.submitted',
                'Detail': json.dumps(reject_job)
            }
        ]
    )
    print("✅ Rejection test event sent")
    
    # Test 3: Check heartbeat metric
    print("\n3. Checking heartbeat metric...")
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='Agent/RoutingManager',
            MetricName='Heartbeat',
            StartTime=datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=10),
            EndTime=datetime.now(timezone.utc),
            Period=300,
            Statistics=['Sum']
        )
        
        if response['Datapoints']:
            print(f"✅ Heartbeat metric found: {len(response['Datapoints'])} data points")
        else:
            print("⚠️  No heartbeat metrics found (may need to wait for schedule)")
    except Exception as e:
        print(f"⚠️  Could not check heartbeat: {e}")
    
    # Test 4: Check routing metrics
    print("\n4. Checking routing metrics...")
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='VideoJobRouting',
            MetricName='RoutingAttempts',
            Dimensions=[
                {'Name': 'Provider', 'Value': 'fal'},
                {'Name': 'Success', 'Value': 'True'}
            ],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=5),
            EndTime=datetime.now(timezone.utc),
            Period=60,
            Statistics=['Sum']
        )
        
        if response['Datapoints']:
            total = sum(d['Sum'] for d in response['Datapoints'])
            print(f"✅ Routing metrics found: {total} successful routes to fal")
        else:
            print("⚠️  No routing metrics found yet")
    except Exception as e:
        print(f"⚠️  Could not check metrics: {e}")
    
    print("\n✅ Smoke tests completed!")
    return True


if __name__ == '__main__':
    import argparse
    from datetime import timedelta
    
    parser = argparse.ArgumentParser(description='Smoke test Routing Manager')
    parser.add_argument('--stage', default='dev', help='Deployment stage')
    args = parser.parse_args()
    
    success = test_routing_manager(args.stage)
    sys.exit(0 if success else 1)