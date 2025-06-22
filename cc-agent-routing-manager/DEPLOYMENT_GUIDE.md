# Routing-Manager Deployment Guide

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. SAM CLI installed (v1.100.0+)
3. Python 3.12 installed
4. Access to the following AWS resources:
   - DynamoDB table `Jobs-{Stage}`
   - SQS queues: `FalJobQueue` and `ReplicateJobQueue`
   - EventBridge default event bus

## Step 1: Get Queue URLs

First, retrieve the actual SQS queue URLs:

```bash
# Get FalJobQueue URL
aws sqs get-queue-url --queue-name FalJobQueue --region us-east-1

# Get ReplicateJobQueue URL  
aws sqs get-queue-url --queue-name ReplicateJobQueue --region us-east-1
```

## Step 2: Deploy to Dev

```bash
# Navigate to the agent directory
cd meta-agents/cc-agent-routing-manager

# Run the deployment (it will prompt for queue URLs)
make deploy

# Or provide queue URLs directly:
sam deploy --config-env dev \
  --parameter-overrides \
  "Stage=dev" \
  "FalQueueUrl=https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT_ID/FalJobQueue" \
  "ReplicateQueueUrl=https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT_ID/ReplicateJobQueue"
```

## Step 3: Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name routing-manager-dev \
  --query 'Stacks[0].StackStatus'

# Get function ARN
aws cloudformation describe-stacks \
  --stack-name routing-manager-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`RoutingManagerFunctionArn`].OutputValue' \
  --output text
```

## Step 4: Run Smoke Tests

```bash
# Run the smoke test suite
python scripts/smoke-test.py --stage dev

# Or use make
make smoke-test
```

Expected results:
- ✅ Test event sent successfully
- ✅ Job successfully routed to fal
- ✅ Rejection test event sent
- ✅ Heartbeat metric found
- ✅ Routing metrics found

## Step 5: Verify in Admin Dashboard

After 5 minutes, check the admin dashboard:
1. Navigate to the CC Admin Dashboard
2. Look for "RoutingManager" in the agents list
3. Verify status shows as "Healthy" (green)

## Step 6: Enable in SSM Parameter

Add RoutingManager to the allowed agents list:

```bash
# Get current enabled agents
CURRENT_AGENTS=$(aws ssm get-parameter \
  --name "/contentcraft/agents/enabled" \
  --query 'Parameter.Value' \
  --output text)

# Add RoutingManager to the list
NEW_AGENTS="${CURRENT_AGENTS},RoutingManager"

# Update the parameter
aws ssm put-parameter \
  --name "/contentcraft/agents/enabled" \
  --value "$NEW_AGENTS" \
  --type "StringList" \
  --overwrite
```

## Step 7: Monitor Initial Traffic

Watch the logs for the first few jobs:

```bash
# Tail CloudWatch logs
aws logs tail /aws/lambda/routing-manager-routing-manager --follow

# Check metrics in CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace VideoJobRouting \
  --metric-name RoutingAttempts \
  --dimensions Name=Stage,Value=dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Troubleshooting

### EventBridge Rule Not Triggering
```bash
# Check if rule is enabled
aws events describe-rule \
  --name routing-manager-dev-RoutingManagerFunctionVideoJobSubmitted-* \
  --query 'State'
```

### IAM Permission Issues
```bash
# Check Lambda execution role
aws lambda get-function \
  --function-name routing-manager-routing-manager \
  --query 'Configuration.Role'

# Verify role policies
aws iam list-attached-role-policies \
  --role-name [ROLE_NAME_FROM_ABOVE]
```

### DLQ Messages
```bash
# Check if messages are going to DLQ
aws sqs get-queue-attributes \
  --queue-url [DLQ_URL_FROM_STACK_OUTPUTS] \
  --attribute-names ApproximateNumberOfMessages
```

## Production Deployment

After successful dev testing:

```bash
# Deploy to staging
make deploy-staging

# After staging validation, deploy to prod
make deploy-prod
```

## Rollback Procedure

If issues arise:

```bash
# Rollback to previous version
aws cloudformation cancel-update-stack --stack-name routing-manager-dev

# Or delete and redeploy
aws cloudformation delete-stack --stack-name routing-manager-dev
```