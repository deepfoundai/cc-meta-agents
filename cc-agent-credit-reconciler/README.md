# Credit Reconciler Agent

Agent-01 "Credit Reconciler" - Keeps user credit ledger perfectly aligned with video generation work.

## Overview

This Lambda function reconciles user credits based on video generation events:
- Debits credits when videos are successfully rendered
- Refunds credits when video generation fails
- Runs periodic scans to catch any missed events
- Detects and logs anomalies using LLM assistance

## Architecture

- **Runtime**: Python 3.12 on AWS Lambda
- **Infrastructure**: AWS SAM
- **Event Sources**: 
  - EventBridge rules for `video.rendered` and `video.failed` events
  - Scheduled timer (every 6 hours) for catch-up reconciliation
- **Data Storage**: DynamoDB tables (Jobs, Credits, Ledger)
- **Observability**: CloudWatch Logs, Metrics, and Alarms

## Key Features

- **Idempotent Operations**: Prevents duplicate debits/refunds
- **Atomic Credit Updates**: Uses DynamoDB atomic counters
- **Anomaly Detection**: LLM-powered analysis of unusual transactions
- **High Performance**: p95 cold start < 600ms, runtime < 2s
- **Comprehensive Testing**: 90%+ test coverage with moto mocks

## Deployment

```bash
# Build
sam build

# Deploy to dev
sam deploy --stack-name cc-agent-reconciler-dev --parameter-overrides Environment=dev

# Deploy to prod
sam deploy --stack-name cc-agent-reconciler-prod --parameter-overrides Environment=prod
```

## Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing
```

## Environment Variables

- `JOBS_TABLE`: DynamoDB table for job records
- `CREDITS_TABLE`: DynamoDB table for user credits
- `LEDGER_TABLE`: DynamoDB table for transaction ledger
- `OPENAI_API_KEY`: Retrieved from AWS Secrets Manager
- `LLM_MODEL`: Model to use for anomaly analysis (default: `gpt-4.1`)

## Monitoring

- CloudWatch Alarms for Lambda errors and high adjustment rates
- Structured JSON logging for easy querying
- Custom metrics in the `Reconciler` namespace

## Security

- All credentials stored in AWS Secrets Manager
- Lambda execution role with least-privilege permissions
- Point-in-time recovery enabled on all DynamoDB tables