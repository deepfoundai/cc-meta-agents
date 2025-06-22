#!/usr/bin/env python3
"""
Smoke tests for CC Agent Routing Manager.
Tests basic functionality after deployment.
"""

import json
import time
import argparse
import requests
from typing import Dict, Any
import sys

# Test timeout
TIMEOUT = 30


def test_health_endpoint(api_url: str) -> bool:
    """Test the health check endpoint."""
    print("Testing health endpoint...")
    
    try:
        response = requests.get(
            f"{api_url}health",
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"❌ Health check failed with status {response.status_code}")
            return False
            
        data = response.json()
        
        if data.get('status') != 'healthy':
            print(f"❌ Service is not healthy: {data}")
            return False
            
        print("✅ Health check passed")
        return True
        
    except Exception as e:
        print(f"❌ Health check error: {str(e)}")
        return False


def test_metrics_endpoint(api_url: str) -> bool:
    """Test the metrics endpoint."""
    print("Testing metrics endpoint...")
    
    try:
        response = requests.get(
            f"{api_url}metrics",
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"❌ Metrics endpoint failed with status {response.status_code}")
            return False
            
        data = response.json()
        
        if 'agent_statistics' not in data:
            print(f"❌ Metrics response missing agent_statistics: {data}")
            return False
            
        print("✅ Metrics endpoint passed")
        return True
        
    except Exception as e:
        print(f"❌ Metrics endpoint error: {str(e)}")
        return False


def test_routing_cost_request(api_url: str) -> bool:
    """Test routing a cost-related request."""
    print("Testing cost request routing...")
    
    try:
        request_data = {
            "content": "What are my AWS costs for this month?",
            "priority": "high",
            "context": {
                "userId": "test-user-123"
            }
        }
        
        response = requests.post(
            f"{api_url}route",
            json=request_data,
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"❌ Routing failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
        data = response.json()
        
        # Check expected fields
        if data.get('agent') != 'cost-sentinel':
            print(f"❌ Wrong agent selected: {data.get('agent')}")
            return False
            
        if 'requestId' not in data:
            print(f"❌ Missing requestId in response: {data}")
            return False
            
        print(f"✅ Cost request routed to {data.get('agent')}")
        return True
        
    except Exception as e:
        print(f"❌ Routing test error: {str(e)}")
        return False


def test_routing_credit_request(api_url: str) -> bool:
    """Test routing a credit-related request."""
    print("Testing credit request routing...")
    
    try:
        request_data = {
            "content": "Check my credit balance and reconcile any issues",
            "priority": "medium"
        }
        
        response = requests.post(
            f"{api_url}route",
            json=request_data,
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"❌ Routing failed with status {response.status_code}")
            return False
            
        data = response.json()
        
        if data.get('agent') != 'credit-reconciler':
            print(f"❌ Wrong agent selected: {data.get('agent')}")
            return False
            
        print(f"✅ Credit request routed to {data.get('agent')}")
        return True
        
    except Exception as e:
        print(f"❌ Credit routing test error: {str(e)}")
        return False


def test_invalid_request(api_url: str) -> bool:
    """Test handling of invalid requests."""
    print("Testing invalid request handling...")
    
    try:
        # Test empty body
        response = requests.post(
            f"{api_url}route",
            json={},
            timeout=TIMEOUT
        )
        
        if response.status_code != 400:
            print(f"❌ Expected 400 for empty body, got {response.status_code}")
            return False
            
        # Test missing content
        response = requests.post(
            f"{api_url}route",
            json={"priority": "high"},
            timeout=TIMEOUT
        )
        
        if response.status_code != 400:
            print(f"❌ Expected 400 for missing content, got {response.status_code}")
            return False
            
        print("✅ Invalid request handling passed")
        return True
        
    except Exception as e:
        print(f"❌ Invalid request test error: {str(e)}")
        return False


def test_unknown_content_routing(api_url: str) -> bool:
    """Test routing for unknown content."""
    print("Testing unknown content routing...")
    
    try:
        request_data = {
            "content": "Random unrelated content that doesn't match any patterns",
            "priority": "low"
        }
        
        response = requests.post(
            f"{api_url}route",
            json=request_data,
            timeout=TIMEOUT
        )
        
        if response.status_code != 400:
            print(f"❌ Expected 400 for unknown content, got {response.status_code}")
            return False
            
        data = response.json()
        
        if 'No suitable agent' not in data.get('error', ''):
            print(f"❌ Expected 'No suitable agent' error, got: {data}")
            return False
            
        print("✅ Unknown content handling passed")
        return True
        
    except Exception as e:
        print(f"❌ Unknown content test error: {str(e)}")
        return False


def main():
    """Run all smoke tests."""
    parser = argparse.ArgumentParser(description='Run smoke tests for Routing Manager')
    parser.add_argument('--env', required=True, choices=['dev', 'staging', 'prod'],
                       help='Environment to test')
    parser.add_argument('--api-url', help='API Gateway URL (optional)')
    
    args = parser.parse_args()
    
    # Determine API URL
    if args.api_url:
        api_url = args.api_url
    else:
        # Construct from environment
        # This would typically come from stack outputs
        api_url = f"https://api-{args.env}.creativecloud.example.com/routing/"
    
    # Ensure URL ends with /
    if not api_url.endswith('/'):
        api_url += '/'
    
    print(f"\n🚀 Running smoke tests for {args.env} environment")
    print(f"API URL: {api_url}\n")
    
    # Run tests
    tests = [
        test_health_endpoint,
        test_metrics_endpoint,
        test_routing_cost_request,
        test_routing_credit_request,
        test_invalid_request,
        test_unknown_content_routing
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        if test(api_url):
            passed += 1
        else:
            failed += 1
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Test Summary: {passed} passed, {failed} failed")
    print(f"{'='*50}\n")
    
    if failed > 0:
        print("❌ Some tests failed!")
        sys.exit(1)
    else:
        print("✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()