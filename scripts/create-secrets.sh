#!/bin/bash

# Script to create AWS Secrets Manager secrets for meta-agents

echo "Creating AWS Secrets Manager secrets..."

# Check if secrets already exist
check_secret() {
    aws secretsmanager describe-secret --secret-id "$1" --region us-east-1 &>/dev/null
    return $?
}

# OpenAI API Key
if check_secret "meta-agents/openai"; then
    echo "✓ OpenAI secret already exists"
else
    echo "Creating OpenAI secret..."
    aws secretsmanager create-secret \
        --name "meta-agents/openai" \
        --description "OpenAI API key for meta-agents" \
        --secret-string '{"api_key": "your-openai-api-key-here"}' \
        --region us-east-1
    echo "✓ OpenAI secret created"
fi

# FAL API Key - Development
if check_secret "/contentcraft/dev/fal/api_key"; then
    echo "✓ FAL dev secret already exists"
else
    echo "Creating FAL dev secret..."
    aws secretsmanager create-secret \
        --name "/contentcraft/dev/fal/api_key" \
        --description "FAL.ai API key for development" \
        --secret-string '{"api_key": "your-fal-api-key-here"}' \
        --region us-east-1
    echo "✓ FAL dev secret created"
fi

# FAL API Key - Production
if check_secret "/contentcraft/prod/fal/api_key"; then
    echo "✓ FAL prod secret already exists"
else
    echo "Creating FAL prod secret..."
    aws secretsmanager create-secret \
        --name "/contentcraft/prod/fal/api_key" \
        --description "FAL.ai API key for production" \
        --secret-string '{"api_key": "your-fal-api-key-here"}' \
        --region us-east-1
    echo "✓ FAL prod secret created"
fi

echo ""
echo "All secrets created successfully!"
echo ""
echo "Remember to update the secrets with actual API keys:"
echo "  aws secretsmanager update-secret --secret-id meta-agents/openai --secret-string '{\"api_key\": \"sk-...\"}'"
echo "  aws secretsmanager update-secret --secret-id /contentcraft/dev/fal/api_key --secret-string '{\"api_key\": \"fal_...\"}'"