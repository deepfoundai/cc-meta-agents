# DevOps-Automation Agent Runbook

The DevOps-Automation Agent (`cc-agent-devops-automation`) serves as the central control plane for infrastructure, CI/CD, and repository hygiene across the ContentCraft ecosystem.

## Quick Reference

- **Agent Name**: `DevOpsAutomation`
- **CloudWatch Namespace**: `Agent/DevOpsAutomation`
- **Heartbeat Frequency**: Every 5 minutes
- **Repository**: `meta-agents/cc-agent-devops-automation/`

## Setup Scripts Locations

### Primary Scripts
- **Deployment**: `scripts/deploy.sh`
- **Dependencies Setup**: `meta-agents/scripts/setup-dependencies.sh`
- **Secrets Creation**: `meta-agents/scripts/create-secrets.sh`

### Infrastructure Setup
```bash
# From meta-agents/cc-agent-devops-automation/
make deploy STAGE=prod              # Deploy to production
make deploy STAGE=dev               # Deploy to development
make test                          # Run unit tests
make integration-test              # Run integration tests
```

### GitHub CLI Setup
```bash
# Required for GitHub operations
gh auth login --scopes repo,workflow,admin:org
export GITHUB_TOKEN=$(gh auth token)
```

## Core Capabilities

### 1. Ecosystem Registration
- Automatically registers itself in `/contentcraft/agents/enabled` SSM parameter
- Publishes heartbeat metrics for admin dashboard discovery
- Self-registers on every Lambda invocation (idempotent)

### 2. GitHub Repository Management
- **Branch Protection**: Validates PR review requirements and status checks
- **Dependabot Configuration**: Ensures security update automation is enabled
- **Workflow Monitoring**: Creates issues for failed GitHub Actions

### 3. Infrastructure Monitoring
- **Heartbeat Metrics**: `Agent/DevOpsAutomation/Heartbeat` every 5 minutes
- **Error Tracking**: Publishes failure metrics on exceptions
- **Health Checks**: Responds to admin dashboard queries

## Triggering Jobs

### Manual Branch Protection Job
```bash
# Via AWS CLI
aws lambda invoke \
  --function-name cc-agent-devops-automation-prod \
  --payload '{"task_type": "github_repo_check", "repository": "cc-agent-doc-registry"}' \
  response.json

# Via SAM Local
sam local invoke DevOpsAutomationFunction \
  --event events/github_repo_check.json
```

### Manual Workflow Monitor
```bash
aws lambda invoke \
  --function-name cc-agent-devops-automation-prod \
  --payload '{"task_type": "workflow_monitor", "repository": "cc-agent-doc-registry", "workflow": "update-registry.yml"}' \
  response.json
```

### Health Check
```bash
aws lambda invoke \
  --function-name cc-agent-devops-automation-prod \
  --payload '{"task_type": "health_check"}' \
  response.json
```

## Phase-2 MRR Reporter Deployment

### Prerequisites
1. **Stripe API Key**: Must exist in Secrets Manager
   ```bash
   # Create the reporting API key secret
   aws secretsmanager create-secret \
     --name "/contentcraft/stripe/reporting_api_key" \
     --description "Stripe restricted API key for MRR reporting" \
     --secret-string "rk_live_YOUR_RESTRICTED_KEY_HERE"
   ```

2. **Email Configuration**: Ensure SNS topic exists
   ```bash
   # The template will auto-subscribe todd@deepfoundai.com and harvey@deepfoundai.com
   # Verify topic exists:
   aws sns list-topics | grep ops-cost-alerts
   ```

### Deployment Steps
```bash
cd meta-agents/cc-agent-devops-automation/

# 1. Build and validate
sam build
sam validate

# 2. Deploy to production
make deploy STAGE=prod

# 3. Verify MRR function deployed
aws lambda get-function --function-name StripeMrrReporterFn-prod

# 4. Test MRR calculation (manual trigger)
aws lambda invoke \
  --function-name StripeMrrReporterFn-prod \
  response.json && cat response.json
```

### MRR Verification
The MRR Reporter runs daily at 06:00 UTC. To verify:

```bash
# Check DynamoDB for MRR data
aws dynamodb get-item \
  --table-name BillingMetrics-prod \
  --key '{"PK":{"S":"mrr"},"SK":{"S":"latest"}}'

# Check CloudWatch logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/StripeMrrReporterFn"
aws logs filter-log-events \
  --log-group-name "/aws/lambda/StripeMrrReporterFn-prod" \
  --start-time $(date -d "1 day ago" +%s)000
```

## EventBridge DevOps API Operations

### Overview
The DevOps-Automation Agent provides a centralized EventBridge-based API for privileged operations. Other agents can request DevOps tasks by publishing `devops.request` events.

### Supported Actions

#### 1. putSecret - Secret Management
Create or update AWS Secrets Manager secrets:
```bash
# Test putSecret request
aws events put-events --entries '[{
  "Source": "agent.TestAgent",
  "DetailType": "devops.request",
  "Detail": "{\"requestId\":\"test-123\",\"action\":\"putSecret\",\"stage\":\"dev\",\"params\":{\"name\":\"/contentcraft/test/secret\",\"value\":\"test-value\"},\"requestedBy\":\"TestAgent\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%S)Z\"}"
}]'
```

#### 2. deployLambda - Stack Deployment
Trigger CloudFormation stack updates:
```bash
# Test deployLambda request
aws events put-events --entries '[{
  "Source": "agent.TestAgent", 
  "DetailType": "devops.request",
  "Detail": "{\"requestId\":\"test-456\",\"action\":\"deployLambda\",\"stage\":\"dev\",\"params\":{\"stackName\":\"test-stack\"},\"requestedBy\":\"TestAgent\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%S)Z\"}"
}]'
```

### Monitoring DevOps Requests
```bash
# Monitor completion events
aws logs filter-log-events \
  --log-group-name /aws/lambda/cc-agent-devops-automation-prod \
  --filter-pattern "devops.completed" \
  --start-time $(date -d '1 hour ago' +%s)000

# Check EventBridge rules
aws events list-rules --name-prefix "cc-agent-devops"
```

### Local Testing EventBridge Integration
```bash
# Test putSecret locally
sam local invoke DevOpsAutomationFunction \
  --event tests/events/devops_put_secret.json

# Test deployLambda locally  
sam local invoke DevOpsAutomationFunction \
  --event tests/events/devops_deploy_lambda.json
```

### EventBridge Troubleshooting
1. **Events not processing**: Check EventBridge rule pattern matches
2. **Permission errors**: Verify IAM policies for secrets/CloudFormation
3. **Completion events missing**: Check EventBridge `PutEvents` permissions

## Scheduled Operations

| Schedule | Function | Purpose |
|----------|----------|---------|
| Every 5 minutes | Heartbeat | Ecosystem monitoring |
| 06:00 UTC daily | MRR Reporter | Stripe revenue calculation |
| 07:00 UTC daily | Repo Check | GitHub hygiene validation |
| Every 6 hours | Workflow Monitor | CI/CD failure detection |
| On-demand | EventBridge Requests | Agent-requested DevOps operations |

## Monitoring & Alerts

### CloudWatch Metrics
- `Agent/DevOpsAutomation/Heartbeat`: Agent health status
- Custom metrics published by MRR Reporter
- Lambda execution metrics (duration, errors, invocations)

### Log Groups
- `/aws/lambda/cc-agent-devops-automation-{stage}`
- `/aws/lambda/StripeMrrReporterFn-{stage}`
- `/aws/lambda/email-subscription-handler-{stage}`

### SNS Topics
- `ops-cost-alerts`: Cost-related notifications
- Auto-subscribed emails: todd@deepfoundai.com, harvey@deepfoundai.com

## Troubleshooting

### Agent Not Showing in Admin Dashboard
1. Check SSM parameter: `aws ssm get-parameter --name /contentcraft/agents/enabled`
2. Verify heartbeat metrics: Check CloudWatch `Agent/DevOpsAutomation/Heartbeat`
3. Review Lambda logs for registration errors

### GitHub Operations Failing
1. Verify `GITHUB_TOKEN_SECRET` exists in Secrets Manager
2. Check GitHub CLI authentication: `gh auth status`
3. Ensure proper repository permissions

### MRR Reporter Issues
1. Verify Stripe API key: `aws secretsmanager get-secret-value --secret-id /contentcraft/stripe/reporting_api_key`
2. Check DynamoDB table exists: `aws dynamodb describe-table --table-name BillingMetrics-prod`
3. Review Lambda timeout settings (current: 5 minutes)

### Cost-Sentinel Integration Issues
1. Ensure DynamoDB permissions match between services
2. Verify EventBridge events are being published
3. Check table naming consistency: `BillingMetrics-${Environment}`

## Development & Testing

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run unit tests
pytest tests/ -v

# Run integration tests
pytest tests/test_integration.py -v

# Local invoke with SAM
sam local start-api
sam local invoke DevOpsAutomationFunction --event events/health_check.json
```

### Creating Test Events
Example event files in `tests/events/`:
- `health_check.json`
- `github_repo_check.json`
- `workflow_monitor.json`

### Environment Variables
- `STAGE`: Deployment stage (dev/prod)
- `GITHUB_TOKEN_SECRET`: SSM path to GitHub token
- `BILLING_METRICS_TABLE`: DynamoDB table name

## Integration with Other Agents

The DevOps-Automation Agent integrates with:
- **Admin Dashboard**: Auto-discovery via SSM parameter
- **Cost-Sentinel**: Provides MRR data for spend/revenue ratios
- **All Agents**: Central heartbeat monitoring system

## Security Considerations

- **Minimal IAM Permissions**: Only required AWS services
- **Secret Isolation**: Stripe keys in dedicated Secrets Manager entries
- **Environment Separation**: Stage-specific resource naming
- **GitHub Token Scope**: Limited to necessary repository operations

---

**Last Updated**: $(date)
**Version**: 1.0
**Maintainer**: DevOps-Automation Agent 