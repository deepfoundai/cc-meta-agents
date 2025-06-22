#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "🚀 Deploying CC Agent DevOps Automation..."

# Parse arguments
STAGE=${1:-dev}
STACK_NAME="cc-agent-devops-automation-${STAGE}"

echo "📦 Building Lambda layer..."
cd "$PROJECT_DIR/layers"
pip install -r requirements.txt -t python/
cd "$PROJECT_DIR"

echo "🔧 Validating SAM template..."
sam validate --template template.yaml

echo "📦 Building SAM application..."
sam build --template template.yaml

echo "🚀 Deploying to AWS..."
sam deploy \
    --stack-name "$STACK_NAME" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides Stage="$STAGE" \
    --no-confirm-changeset \
    --no-fail-on-empty-changeset

echo "✅ Deployment complete!"

# Get function ARNs
DEVOPS_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='DevOpsAutomationFunctionArn'].OutputValue" \
    --output text)

MRR_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='StripeMrrReporterFunctionArn'].OutputValue" \
    --output text)

echo "📋 Deployed functions:"
echo "  - DevOps Automation: $DEVOPS_ARN"
echo "  - MRR Reporter: $MRR_ARN"