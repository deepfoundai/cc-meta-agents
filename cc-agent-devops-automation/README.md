# CC Agent DevOps Automation

> **🔧 MAINTENANCE MODE** - Phase 2 complete. Monitor-only operations until next infrastructure epic.

The DevOps-Automation Agent serves as the **central control plane** for infrastructure, CI/CD, and repository hygiene across the ContentCraft ecosystem.

## Status: Production Stable ✅

- **Version**: 2.0 (EventBridge DevOps API)
- **Mode**: Maintenance/Monitor-Only
- **Last Updated**: 2025-06-21
- **Next Epic**: Routing-Manager (TBD)

## Core Capabilities

### 🔄 Ecosystem Integration
- **Agent Registration**: Auto-registers in `/contentcraft/agents/enabled` SSM parameter for admin dashboard discovery
- **Heartbeat Monitoring**: Publishes `Agent/DevOpsAutomation/Heartbeat` metrics every 5 minutes
- **Health Checks**: Responds to admin dashboard queries with capability information

### 📊 MRR Reporting
- **Stripe Integration**: Calculates Monthly Recurring Revenue from Stripe transactions
- **DynamoDB Storage**: Stores MRR data in `BillingMetrics-{Stage}` table  
- **Cost-Sentinel Integration**: Provides MRR data for spend/revenue ratio alerts
- **Daily Schedule**: Runs at 06:00 UTC daily

### 🔧 GitHub Repository Management
- **Branch Protection**: Validates PR review requirements and status checks
- **Dependabot Configuration**: Ensures security update automation is enabled
- **Workflow Monitoring**: Creates issues for failed GitHub Actions

### 🎯 EventBridge DevOps API
- **Secret Management**: Create/update AWS Secrets Manager secrets via `putSecret` action
- **Lambda Deployment**: Trigger CloudFormation stack deployments via `deployLambda` action
- **Request Routing**: Process `devops.request` events from other agents
- **Completion Events**: Publish `devops.completed` events with results and latency
- **Audit Trail**: Full request/response logging with requesting agent identification

### 📈 Monitoring & Alerts
- **CloudWatch Metrics**: Heartbeat and operational metrics
- **SNS Integration**: Email alerts to todd@deepfoundai.com and harvey@deepfoundai.com
- **EventBridge Events**: Publishes MRR calculation completion events

## Architecture

Deployed as AWS Lambda functions with multiple triggers:
- **Every 5 minutes**: Heartbeat metric publication
- **06:00 UTC daily**: MRR calculation from Stripe
- **07:00 UTC daily**: Repository health checks  
- **Every 6 hours**: Workflow monitoring
- **EventBridge Events**: `devops.request` events from other agents

## Quick Start

```bash
# Deploy the complete stack
make deploy STAGE=prod

# Verify agent registration
aws ssm get-parameter --name /contentcraft/agents/enabled

# Check heartbeat metrics
aws cloudwatch get-metric-statistics \
  --namespace Agent/DevOpsAutomation \
  --metric-name Heartbeat \
  --start-time $(date -d '1 hour ago' -u +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Prerequisites

1. **Stripe API Key**: Create restricted reporting key in Secrets Manager:
   ```bash
   aws secretsmanager create-secret \
     --name "/contentcraft/stripe/reporting_api_key" \
     --description "Stripe restricted API key for MRR reporting" \
     --secret-string "rk_live_YOUR_RESTRICTED_KEY_HERE"
   ```

2. **GitHub Token**: Store in Secrets Manager at `/contentcraft/github/token`

3. **SNS Topic**: Ensure `ops-cost-alerts` topic exists for email subscriptions

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Validate template
sam validate

# Build (requires Python 3.11)
sam build

# Local testing
sam local invoke DevOpsAutomationFunction --event tests/events/health_check.json
sam local invoke DevOpsAutomationFunction --event tests/events/devops_put_secret.json
sam local invoke DevOpsAutomationFunction --event tests/events/devops_deploy_lambda.json
sam local invoke StripeMrrReporterFunction --event tests/events/mrr_calculation.json

# Run tests
pytest tests/ -v
```

## Integration Points

- **Admin Dashboard**: Auto-discovery via SSM parameter and heartbeat metrics
- **Cost-Sentinel**: Provides MRR data for spend/revenue ratio calculations
- **Billing-Tiers**: Consumes Stripe data for revenue reporting
- **All Agents**: Central heartbeat monitoring for ecosystem health

## Monitoring

### CloudWatch Metrics
- `Agent/DevOpsAutomation/Heartbeat`: Agent health (every 5 minutes)
- Lambda execution metrics (duration, errors, invocations)

### Log Groups
- `/aws/lambda/cc-agent-devops-automation-{stage}`
- `/aws/lambda/StripeMrrReporterFn-{stage}`

### DynamoDB Tables
- `BillingMetrics-{Stage}`: MRR data storage (PK: 'mrr', SK: 'latest')

### Alerting (Maintenance Mode)
- **SNS Topic**: `ops-cost-alerts`
- **Subscribers**: todd@deepfoundai.com, harvey@deepfoundai.com
- **Triggers**: Lambda failures, heartbeat missed, MRR calculation errors
- **DLQ**: EventBridge request failures surfaced via SNS

## Documentation

- **[RUNBOOK-DEVOPS.md](docs/RUNBOOK-DEVOPS.md)**: Comprehensive operational guide
- **[DEVOPS_INTERFACE.md](docs/DEVOPS_INTERFACE.md)**: EventBridge API documentation
- **[DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md)**: Deployment status and history

## Implementation Status

### ✅ Phase 1 - Hardening (Complete)
- [x] Add heartbeat put_metric_data (CloudWatch)
- [x] Write RUNBOOK-DEVOPS.md
- [x] Update /contentcraft/agents/enabled SSM parameter
- [x] Enhanced health checks with capability reporting
- [x] MRR Reporter Lambda function
- [x] DynamoDB table for billing metrics
- [x] SNS email subscriptions

### ✅ Phase 2 - EventBridge Integration (Complete)
- [x] Implement EventBridge rule "devops.request"
- [x] Support action=putSecret + action=deployLambda
- [x] Request router with completion event publishing
- [x] Unit tests for request→completion flow
- [x] Add docs/DEVOPS_INTERFACE.md
- [x] IAM permissions for secrets and CloudFormation

### 🔧 Maintenance Mode (Current)
- [x] Monitor-only operations
- [x] Heartbeat & registration active
- [x] EventBridge API remains functional
- [x] SNS alerting for failures
- [x] Dependabot security updates enabled

### 📋 Future Phases (Parked)
- [ ] Advanced GitHub hygiene automation
- [ ] Slack webhook integration  
- [ ] Branch protection management
- [ ] Advanced deployment orchestration

> **Note**: New features development paused pending Routing-Manager epic kickoff.

## Version History

- **v1.0**: Enhanced with heartbeat monitoring and ecosystem integration
- **v1.1**: Added MRR Reporter and Cost-Sentinel integration
- **v1.2**: Complete control plane implementation
- **v2.0**: EventBridge DevOps API with secret management and deployment coordination
- **v2.0.1**: Maintenance mode - monitor-only operations