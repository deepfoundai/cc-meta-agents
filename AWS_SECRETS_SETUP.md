# AWS Secrets Manager Setup for Meta-Agents

This document describes how the meta-agents are configured to securely retrieve the OpenAI API key from AWS Secrets Manager.

## Overview

Instead of storing API keys in environment variables or configuration files, all meta-agents retrieve secrets from AWS Secrets Manager at runtime. This provides:

- **Security**: Secrets are encrypted at rest and in transit
- **Rotation**: Easy secret rotation without code changes
- **Audit**: Full audit trail of secret access
- **Centralization**: Single source of truth for all agents

## Architecture

1. **Secrets Manager**: Stores the OpenAI API key in JSON format
2. **Lambda Layer**: Shared Python module for secret retrieval
3. **IAM Policies**: Least-privilege access to specific secrets
4. **Runtime Retrieval**: Secrets fetched and cached during execution

## Secret Structure

The OpenAI API key is stored in AWS Secrets Manager under the name `meta-agents/openai` with the following structure:

```json
{
  "api_key": "sk-proj-..."
}
```

## Setup Instructions

### 1. Create the Secret

Run the provided script to create the secret:

```bash
./scripts/create-secrets.sh
```

Or manually using AWS CLI:

```bash
aws secretsmanager create-secret \
    --name "meta-agents/openai" \
    --description "OpenAI API key for meta-agents" \
    --secret-string '{"api_key": "your-actual-api-key"}' \
    --region us-east-1
```

### 2. Deploy with Secrets Support

Use the deployment script that handles the Lambda layer and permissions:

```bash
./scripts/deploy-with-secrets.sh dev
```

### 3. Update Existing Secret

To update the API key:

```bash
aws secretsmanager put-secret-value \
    --secret-id "meta-agents/openai" \
    --secret-string '{"api_key": "new-api-key"}'
```

## Implementation Details

### Shared Secrets Manager Module

Located at `/shared/secrets_manager.py`, this module provides:

- Singleton pattern for efficient secret retrieval
- In-memory caching to reduce API calls
- Error handling for missing secrets
- Simple interface for getting the OpenAI API key

### Lambda Function Updates

Each Lambda function:

1. Imports the shared secrets module from the Lambda layer
2. Retrieves the API key at runtime when needed
3. Uses IAM role permissions to access only required secrets

### IAM Permissions

Each Lambda function's IAM role includes:

```yaml
- Version: '2012-10-17'
  Statement:
    - Effect: Allow
      Action:
        - secretsmanager:GetSecretValue
      Resource: !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:meta-agents/openai*'
```

## Adding New Agents

When creating new meta-agents:

1. Add the shared Lambda layer to your SAM template:
   ```yaml
   Layers:
     - !Ref SharedLayer
   ```

2. Add the IAM permission for Secrets Manager access

3. Import and use the secrets manager in your code:
   ```python
   import sys
   sys.path.insert(0, '/opt')
   from secrets_manager import secrets_manager
   
   api_key = secrets_manager.get_openai_api_key()
   ```

## Security Best Practices

1. **Never log or print the API key**
2. **Use least-privilege IAM policies**
3. **Enable secret rotation when possible**
4. **Monitor secret access via CloudTrail**
5. **Use resource-based policies on secrets for cross-account access**

## Troubleshooting

### Common Issues

1. **"Access Denied" errors**: Check IAM role permissions
2. **"Secret not found"**: Verify secret name and region
3. **Import errors**: Ensure Lambda layer is attached
4. **API key not working**: Verify the secret value is correctly formatted

### Debug Commands

Check if secret exists:
```bash
aws secretsmanager describe-secret --secret-id meta-agents/openai
```

View Lambda function configuration:
```bash
aws lambda get-function-configuration --function-name cc-agent-reconciler-dev
```

## Cost Considerations

- AWS Secrets Manager charges $0.40 per secret per month
- API calls: $0.05 per 10,000 API calls
- Caching in the Lambda layer minimizes API calls

## Future Enhancements

1. **Secret Rotation**: Implement automatic key rotation
2. **Multiple Keys**: Support for multiple API keys with load balancing
3. **Regional Replication**: Cross-region secret replication for DR
4. **Version Control**: Track secret versions for rollback capability