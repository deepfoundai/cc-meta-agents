#!/bin/bash
# IMMEDIATE CORS FIX - Add OPTIONS to Active APIs
# Run this script to fix CORS in < 5 minutes

set -e

echo "=== IMMEDIATE CORS FIX FOR ACTIVE APIs ==="
echo "This will add OPTIONS methods to the APIs actually used by frontend"
echo

# Fix Credits API (elu5mb5p45)
echo "1. Fixing Credits API (elu5mb5p45)..."

# Get resource ID for /v1/credits/balance
CREDITS_RESOURCE=$(aws apigateway get-resources --rest-api-id elu5mb5p45 \
  --query 'items[?path==`/v1/credits/balance`].id' --output text --region us-east-1)

if [ -z "$CREDITS_RESOURCE" ]; then
  echo "ERROR: Could not find /v1/credits/balance resource"
  exit 1
fi

echo "   Found resource: $CREDITS_RESOURCE"

# Create OPTIONS method
aws apigateway put-method --rest-api-id elu5mb5p45 \
  --resource-id "$CREDITS_RESOURCE" \
  --http-method OPTIONS \
  --authorization-type NONE \
  --no-api-key-required \
  --region us-east-1

echo "   ✓ OPTIONS method created"

# Create method response
aws apigateway put-method-response --rest-api-id elu5mb5p45 \
  --resource-id "$CREDITS_RESOURCE" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{
    "method.response.header.Access-Control-Allow-Origin": false,
    "method.response.header.Access-Control-Allow-Headers": false,
    "method.response.header.Access-Control-Allow-Methods": false
  }' \
  --region us-east-1

# Create MOCK integration
aws apigateway put-integration --rest-api-id elu5mb5p45 \
  --resource-id "$CREDITS_RESOURCE" \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
  --region us-east-1

echo "   ✓ MOCK integration created"

# Create integration response
aws apigateway put-integration-response --rest-api-id elu5mb5p45 \
  --resource-id "$CREDITS_RESOURCE" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{
    "method.response.header.Access-Control-Allow-Origin": "'\''https://video.deepfoundai.com'\''",
    "method.response.header.Access-Control-Allow-Headers": "'\''Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'\''",
    "method.response.header.Access-Control-Allow-Methods": "'\''GET,POST,OPTIONS'\''"
  }' \
  --region us-east-1

echo "   ✓ Integration response configured"

# Deploy
aws apigateway create-deployment --rest-api-id elu5mb5p45 \
  --stage-name v1 \
  --description "Add OPTIONS method for CORS" \
  --region us-east-1

echo "   ✓ Deployed to v1 stage"
echo

# Fix Jobs API (o0fvahtccd)
echo "2. Fixing Jobs API (o0fvahtccd)..."

# Get resource ID for /v1/jobs/overview
JOBS_RESOURCE=$(aws apigateway get-resources --rest-api-id o0fvahtccd \
  --query 'items[?path==`/v1/jobs/overview`].id' --output text --region us-east-1)

if [ -z "$JOBS_RESOURCE" ]; then
  echo "ERROR: Could not find /v1/jobs/overview resource"
  exit 1
fi

echo "   Found resource: $JOBS_RESOURCE"

# Create OPTIONS method
aws apigateway put-method --rest-api-id o0fvahtccd \
  --resource-id "$JOBS_RESOURCE" \
  --http-method OPTIONS \
  --authorization-type NONE \
  --no-api-key-required \
  --region us-east-1

echo "   ✓ OPTIONS method created"

# Create method response
aws apigateway put-method-response --rest-api-id o0fvahtccd \
  --resource-id "$JOBS_RESOURCE" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{
    "method.response.header.Access-Control-Allow-Origin": false,
    "method.response.header.Access-Control-Allow-Headers": false,
    "method.response.header.Access-Control-Allow-Methods": false
  }' \
  --region us-east-1

# Create MOCK integration
aws apigateway put-integration --rest-api-id o0fvahtccd \
  --resource-id "$JOBS_RESOURCE" \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
  --region us-east-1

echo "   ✓ MOCK integration created"

# Create integration response
aws apigateway put-integration-response --rest-api-id o0fvahtccd \
  --resource-id "$JOBS_RESOURCE" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters '{
    "method.response.header.Access-Control-Allow-Origin": "'\''https://video.deepfoundai.com'\''",
    "method.response.header.Access-Control-Allow-Headers": "'\''Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'\''",
    "method.response.header.Access-Control-Allow-Methods": "'\''GET,POST,OPTIONS'\''"
  }' \
  --region us-east-1

echo "   ✓ Integration response configured"

# Deploy
aws apigateway create-deployment --rest-api-id o0fvahtccd \
  --stage-name v1 \
  --description "Add OPTIONS method for CORS" \
  --region us-east-1

echo "   ✓ Deployed to v1 stage"
echo

echo "=== VALIDATION ==="
echo "Testing CORS preflight requests..."
echo

# Test both APIs
for url in \
  "https://elu5mb5p45.execute-api.us-east-1.amazonaws.com/v1/credits/balance" \
  "https://o0fvahtccd.execute-api.us-east-1.amazonaws.com/v1/jobs/overview"; do
  
  echo -n "Testing $url ... "
  
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS \
    -H "Origin: https://video.deepfoundai.com" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Authorization,Content-Type" \
    "$url")
  
  if [ "$STATUS" = "200" ] || [ "$STATUS" = "204" ]; then
    echo -e "\033[0;32m✓ PASS (HTTP $STATUS)\033[0m"
  else
    echo -e "\033[0;31m✗ FAIL (HTTP $STATUS)\033[0m"
  fi
done

echo
echo "=== CORS FIX COMPLETE ==="
echo "If tests show PASS, CORS is now working!"
echo "Please test at https://video.deepfoundai.com"