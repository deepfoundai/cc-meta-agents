# Deployment Guide for Credit Reconciler

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS SAM CLI** installed (version 1.100.0+)
3. **Python 3.12** installed
4. **Docker** running (for SAM build)
5. **Appropriate AWS permissions** for Lambda, DynamoDB, EventBridge, CloudWatch, and Secrets Manager

## Quick Start

```bash
# Deploy to dev environment and run smoke tests
make dev
```

## Step-by-Step Deployment

### 1. Install Dependencies
```bash
make install
```

### 2. Run Unit Tests
```bash
make test
```

### 3. Build the SAM Application
```bash
make build
```

### 4. Deploy to AWS
```bash
# Deploy to dev (default)
make deploy

# Deploy to staging
make deploy ENVIRONMENT=staging

# Deploy to production
make deploy ENVIRONMENT=prod
```

### 5. Run Smoke Tests
```bash
# Test dev environment
make smoke-test

# Test specific environment
make smoke-test ENVIRONMENT=staging
```

## Manual Deployment Steps

If you prefer to run commands manually:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run tests
python -m pytest tests/ -v

# 3. Build SAM
sam build --use-container

# 4. Deploy
sam deploy --guided  # First time
sam deploy          # Subsequent deployments

# 5. Run smoke tests
python scripts/smoke-test.py --env dev
```

## Configuration

### Environment Variables (set in template.yaml)
- `OPENAI_API_KEY`: Retrieved from AWS Secrets Manager
- `LLM_MODEL`: Model for anomaly analysis (default: gpt-4.1)

### Required AWS Secrets
Create these in AWS Secrets Manager before deployment:
```bash
# OpenAI API Key
aws secretsmanager create-secret \
  --name fertilia/openai \
  --secret-string '{"api_key":"sk-..."}'
```

### SSM Parameters for Pricing
```bash
# Default model pricing
aws ssm put-parameter \
  --name /fertilia/pricing/default \
  --value "0.10" \
  --type String

# Premium model pricing
aws ssm put-parameter \
  --name /fertilia/pricing/premium \
  --value "0.25" \
  --type String
```

## Monitoring

After deployment, monitor the function:

1. **CloudWatch Logs**
   - Log group: `/aws/lambda/cc-agent-reconciler-{env}`
   - Filter for errors: `{ $.level = "error" }`

2. **CloudWatch Metrics**
   - AWS/Lambda namespace: Errors, Duration, Invocations
   - Reconciler namespace: Adjustments

3. **CloudWatch Alarms**
   - Lambda errors threshold
   - High adjustment rate alert

## Troubleshooting

### Common Issues

1. **SAM build fails**
   - Ensure Docker is running
   - Check Python version is 3.12

2. **Deployment fails**
   - Check AWS credentials
   - Verify S3 bucket exists for SAM artifacts
   - Check CloudFormation stack status

3. **Smoke tests fail**
   - Verify Lambda was deployed successfully
   - Check DynamoDB tables were created
   - Review CloudWatch logs for errors

### Debug Commands

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name cc-agent-reconciler-dev

# View Lambda logs
aws logs tail /aws/lambda/cc-agent-reconciler-dev --follow

# Invoke Lambda manually
aws lambda invoke \
  --function-name cc-agent-reconciler-dev \
  --payload '{"source":"aws.events","detail-type":"test"}' \
  response.json
```

## Rollback

If issues occur after deployment:

```bash
# Rollback to previous version
aws cloudformation cancel-update-stack \
  --stack-name cc-agent-reconciler-prod

# Or delete and redeploy
sam delete --stack-name cc-agent-reconciler-dev
```