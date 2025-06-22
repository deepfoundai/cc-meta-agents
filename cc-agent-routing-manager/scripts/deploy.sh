#!/bin/bash
set -e

# Deploy Routing Manager Agent

STAGE=${1:-dev}
FAL_QUEUE_URL=${2:-}
REPLICATE_QUEUE_URL=${3:-}

echo "Deploying Routing Manager to stage: $STAGE"

# Validate template
echo "Validating SAM template..."
sam validate

# Build
echo "Building Lambda function..."
sam build

# Deploy
echo "Deploying to AWS..."
if [ "$STAGE" == "dev" ]; then
    # For dev, use provided URLs or prompt
    if [ -z "$FAL_QUEUE_URL" ]; then
        read -p "Enter FAL Queue URL: " FAL_QUEUE_URL
    fi
    if [ -z "$REPLICATE_QUEUE_URL" ]; then
        read -p "Enter Replicate Queue URL: " REPLICATE_QUEUE_URL
    fi
    
    sam deploy --config-env dev \
        --resolve-s3 \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
        "Stage=$STAGE" \
        "FalQueueUrl=$FAL_QUEUE_URL" \
        "ReplicateQueueUrl=$REPLICATE_QUEUE_URL"
else
    sam deploy --config-env $STAGE
fi

echo "Deployment complete!"

# Get stack outputs
aws cloudformation describe-stacks \
    --stack-name routing-manager-$STAGE \
    --query 'Stacks[0].Outputs' \
    --output table

echo "Run 'python scripts/smoke-test.py' to test the deployment"