#!/bin/bash

# Deploy meta-agents with AWS Secrets Manager setup

set -e

echo "=== Meta-agents Deployment with Secrets Manager ==="

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS CLI is not configured properly"
    exit 1
fi

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${1:-dev}

echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"
echo "Environment: $ENVIRONMENT"

# Create or update the secret
echo ""
echo "=== Setting up AWS Secrets Manager ==="
SECRET_NAME="meta-agents/openai"

# Check if secret exists
if aws secretsmanager describe-secret --secret-id $SECRET_NAME --region $AWS_REGION &> /dev/null; then
    echo "Secret $SECRET_NAME already exists. Run create-secrets.sh to update it."
else
    echo "Creating secret $SECRET_NAME..."
    # Note: In production, you should pass the API key as a parameter or environment variable
    # For now, we'll create it without a value and you can update it manually
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "OpenAI API key for meta-agents" \
        --secret-string '{"api_key": "PLACEHOLDER_UPDATE_ME"}' \
        --region $AWS_REGION
    
    echo "WARNING: Secret created with placeholder value. Please update it with the actual API key:"
    echo "aws secretsmanager put-secret-value --secret-id $SECRET_NAME --secret-string '{\"api_key\": \"your-actual-key\"}'"
fi

# Create shared layer directory structure
echo ""
echo "=== Preparing shared Lambda layer ==="
mkdir -p shared/python
cp shared/secrets_manager.py shared/python/

# Install dependencies for the layer
pip install boto3 -t shared/python/ --quiet

# Deploy credit reconciler
echo ""
echo "=== Deploying Credit Reconciler Agent ==="
cd cc-agent-credit-reconciler
sam build
sam deploy \
    --stack-name cc-agent-credit-reconciler-$ENVIRONMENT \
    --parameter-overrides Environment=$ENVIRONMENT \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --region $AWS_REGION

cd ..

# Deploy prompt curator
echo ""
echo "=== Deploying Prompt Curator Agent ==="
cd cc-agent-prompt-curator
sam build
sam deploy \
    --stack-name cc-agent-prompt-curator-$ENVIRONMENT \
    --parameter-overrides Environment=$ENVIRONMENT \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --region $AWS_REGION

cd ..

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "1. Update the OpenAI API key in Secrets Manager (if not already done):"
echo "   aws secretsmanager put-secret-value --secret-id $SECRET_NAME --secret-string '{\"api_key\": \"your-actual-key\"}'"
echo ""
echo "2. Test the agents with their smoke test scripts:"
echo "   python cc-agent-credit-reconciler/scripts/smoke-test.py"
echo "   python cc-agent-prompt-curator/smoke-test.py"
echo ""
echo "3. Monitor CloudWatch logs for any errors"