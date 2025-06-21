#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-dev}
REGION=${AWS_REGION:-us-east-1}

echo -e "${GREEN}🚀 Deploying Credit Reconciler to ${ENVIRONMENT} environment${NC}"
echo "Region: ${REGION}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}❌ Invalid environment: $ENVIRONMENT${NC}"
    echo "Usage: $0 [dev|staging|prod]"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &>/dev/null; then
    echo -e "${RED}❌ AWS credentials not configured${NC}"
    exit 1
fi

# Install dependencies
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
pip install -r requirements.txt -t src/

# Run tests
echo -e "${YELLOW}🧪 Running tests...${NC}"
python -m pytest tests/ -v

# Build SAM application
echo -e "${YELLOW}🔨 Building SAM application...${NC}"
sam build --use-container

# Validate template
echo -e "${YELLOW}✅ Validating SAM template...${NC}"
sam validate

# Deploy
echo -e "${YELLOW}🚀 Deploying to AWS...${NC}"
if [ "$ENVIRONMENT" == "prod" ]; then
    # Production requires confirmation
    sam deploy --config-env prod
else
    # Dev/staging auto-confirm
    sam deploy --no-confirm-changeset \
        --stack-name "cc-agent-reconciler-${ENVIRONMENT}" \
        --parameter-overrides "Environment=${ENVIRONMENT}"
fi

# Get stack outputs
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo -e "${YELLOW}📊 Stack outputs:${NC}"
aws cloudformation describe-stacks \
    --stack-name "cc-agent-reconciler-${ENVIRONMENT}" \
    --query 'Stacks[0].Outputs' \
    --output table

# Save function ARN for smoke tests
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name "cc-agent-reconciler-${ENVIRONMENT}" \
    --query 'Stacks[0].Outputs[?OutputKey==`FunctionArn`].OutputValue' \
    --output text)

echo -e "${GREEN}Lambda Function ARN: ${FUNCTION_ARN}${NC}"
echo "export RECONCILER_FUNCTION_ARN=${FUNCTION_ARN}" > .env.${ENVIRONMENT}