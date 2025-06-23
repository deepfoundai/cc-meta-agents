#!/bin/bash

# DevOps-Debug Agent CORS Investigation Script
# Purpose: Gather evidence for CORS Root Cause Analysis

echo "=== DEVOPS-DEBUG AGENT CORS INVESTIGATION ==="
echo "Starting at: $(date)"
echo

# 1. DNS Resolution
echo "=== DNS RESOLUTION ==="
nslookup video.deepfoundai.com
echo

# 2. Check env.js served to browser
echo "=== ENV.JS API CONFIGURATION ==="
curl -s https://video.deepfoundai.com/_app/env.js | grep -E "API_URL|CREDITS_API|JOBS_API" || echo "No env.js found"
echo

# 3. Pre-flight checks for all APIs
echo "=== PREFLIGHT OPTIONS TESTS ==="
for url in \
  "https://hxk5lx2y17.execute-api.us-east-1.amazonaws.com/v1/credits/balance" \
  "https://6ydbgbao92.execute-api.us-east-1.amazonaws.com/v1/jobs/overview" \
  "https://elu5mb5p45.execute-api.us-east-1.amazonaws.com/v1/credits/balance" \
  "https://o0fvahtccd.execute-api.us-east-1.amazonaws.com/v1/jobs/overview"; do
  echo "--- Testing: $url ---"
  curl -i -X OPTIONS \
    -H "Origin: https://video.deepfoundai.com" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Authorization,Content-Type" \
    "$url" 2>/dev/null | head -n 20
  echo
done

# 4. CloudFront Distribution Info
echo "=== CLOUDFRONT DISTRIBUTION ==="
# First find the distribution ID
DISTRO_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Aliases.Items[?contains(@,'video.deepfoundai.com')]].Id" --output text 2>/dev/null)
if [ ! -z "$DISTRO_ID" ]; then
  echo "Distribution ID: $DISTRO_ID"
  aws cloudfront get-distribution --id "$DISTRO_ID" --query '{DomainName:Distribution.DomainName,Origins:DistributionConfig.Origins.Items[*].{Id:Id,DomainName:DomainName}}' --output json
else
  echo "No CloudFront distribution found for video.deepfoundai.com"
fi
echo

# 5. API Gateway Configuration
echo "=== API GATEWAY CONFIGURATION ==="
echo "--- REST APIs ---"
aws apigateway get-rest-apis --region us-east-1 --query 'items[?id==`hxk5lx2y17` || id==`6ydbgbao92` || id==`elu5mb5p45` || id==`o0fvahtccd`].{id:id,name:name,apiKeySource:apiKeySource,policy:policy}' --output table
echo

# 6. Detailed API analysis for problematic APIs
echo "=== DETAILED API ANALYSIS ==="
for api_id in "hxk5lx2y17" "6ydbgbao92"; do
  echo "--- API: $api_id ---"
  
  # Get resources
  echo "Resources:"
  aws apigateway get-resources --rest-api-id "$api_id" --region us-east-1 --query 'items[?path==`/v1/credits/balance` || path==`/v1/jobs/overview`].{path:path,id:id}' --output table
  
  # Check for OPTIONS method on /v1/credits/balance
  RESOURCE_ID=$(aws apigateway get-resources --rest-api-id "$api_id" --region us-east-1 --query 'items[?path==`/v1/credits/balance`].id' --output text 2>/dev/null)
  if [ ! -z "$RESOURCE_ID" ]; then
    echo "OPTIONS method for /v1/credits/balance:"
    aws apigateway get-method --rest-api-id "$api_id" --resource-id "$RESOURCE_ID" --http-method OPTIONS --region us-east-1 2>/dev/null || echo "No OPTIONS method found"
  fi
  
  # Check gateway responses
  echo "Gateway Responses:"
  aws apigateway get-gateway-responses --rest-api-id "$api_id" --region us-east-1 --query 'items[?responseType==`DEFAULT_4XX` || responseType==`MISSING_AUTHENTICATION_TOKEN`].{type:responseType,headers:responseParameters}' --output json
  echo
done

# 7. Compare with working APIs
echo "=== WORKING API ANALYSIS ==="
for api_id in "elu5mb5p45" "o0fvahtccd"; do
  echo "--- API: $api_id ---"
  
  # Get deployment stage info
  STAGE=$(aws apigateway get-stages --rest-api-id "$api_id" --region us-east-1 --query 'item[0].stageName' --output text 2>/dev/null)
  if [ ! -z "$STAGE" ]; then
    echo "Stage: $STAGE"
    aws apigateway get-stage --rest-api-id "$api_id" --stage-name "$STAGE" --region us-east-1 --query '{methodSettings:methodSettings}' --output json
  fi
  echo
done

echo "=== INVESTIGATION COMPLETE ==="
echo "Completed at: $(date)"