# CC Agent MRR Reporter

A Lambda function that generates Monthly Recurring Revenue (MRR) reports from Stripe subscription data.

## Features

- Calculates total MRR from all active Stripe subscriptions
- Provides breakdown by subscription plan
- Handles both monthly and annual billing intervals
- Scheduled daily reports via EventBridge
- On-demand report generation via API Gateway
- Optional SNS notifications for report delivery

## Architecture

This Lambda function:
1. Retrieves Stripe API credentials from AWS Secrets Manager
2. Fetches all active subscriptions from Stripe
3. Calculates MRR considering different billing intervals
4. Generates a detailed report with plan breakdown
5. Optionally publishes the report to SNS

## Prerequisites

- AWS SAM CLI installed
- AWS credentials configured
- Stripe API key stored in AWS Secrets Manager at `cc-agent/stripe`

## Deployment

```bash
# Build the Lambda function
sam build

# Deploy to AWS
sam deploy --guided

# For production deployment
sam deploy --config-env prod
```

## Configuration

### Environment Variables
- `SNS_TOPIC_ARN`: (Optional) SNS topic for report notifications
- `LOG_LEVEL`: Logging level (default: INFO)

### AWS Secrets Manager
The function expects a secret named `cc-agent/stripe` with the following structure:
```json
{
  "api_key": "sk_live_..."
}
```

## Usage

### Scheduled Reports
The function runs automatically every day at 9 AM UTC.

### On-Demand Reports
```bash
# Get MRR report via API
curl -X GET https://{api-id}.execute-api.{region}.amazonaws.com/prod/mrr-report \
  --aws-sigv4 "aws:amz:{region}:execute-api"
```

### Report Format
```json
{
  "timestamp": "2024-01-20T09:00:00Z",
  "total_mrr": 12500.00,
  "active_subscriptions": 150,
  "plan_breakdown": {
    "Pro Plan": {
      "count": 100,
      "mrr": 10000.00
    },
    "Basic Plan": {
      "count": 50,
      "mrr": 2500.00
    }
  },
  "currency": "USD"
}
```

## Development

### Local Testing
```bash
# Install dependencies
pip install -r src/requirements.txt -t src/

# Run local tests
sam local start-api
```

### Monitoring
- CloudWatch Logs: `/aws/lambda/cc-agent-mrr-reporter-{stage}-MRRReporterFunction-*`
- CloudWatch Metrics: Lambda invocations, errors, duration

## Security

- Uses IAM authentication for API access
- Stripe credentials stored in AWS Secrets Manager
- Minimal IAM permissions following least privilege principle