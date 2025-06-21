# Credit Reconciler Agent v1.0

Enterprise-grade credit reconciliation service with production hardening, DLQ, and alarm integrations.

## Overview

The Credit Reconciler Agent ensures that user credit balances stay synchronized with video generation activities. It processes `video.rendered` and `video.failed` events, automatically debiting and refunding credits with full audit trail support.

## Architecture

### Core Components
- **Lambda Function**: Event-driven credit processing
- **DynamoDB Tables**: Credits, Jobs, and Ledger storage
- **Dead Letter Queue**: Failed event recovery
- **CloudWatch Alarms**: Error monitoring and alerting
- **SNS Topic**: Operational notifications

### Event Flow
1. Video generation events trigger Lambda via EventBridge
2. Lambda processes credit adjustments atomically
3. All transactions logged to audit ledger
4. Failed events sent to DLQ for investigation
5. Errors trigger CloudWatch alarms and SNS notifications

## Deployment

### Environments
- **dev**: Development environment with test data
- **staging**: Pre-production validation environment  
- **prod**: Production environment with live data

### Quick Deploy
```bash
# Deploy to development
sam build && sam deploy --config-env default

# Deploy to production
sam build && sam deploy --config-env prod

# Deploy to staging
sam build && sam deploy --config-env staging
```

### Stack Resources

#### Lambda Function
- **Name**: `cc-agent-reconciler-{stage}`
- **Runtime**: Python 3.12
- **Memory**: 512MB
- **Timeout**: 30 seconds
- **Concurrency**: 10 reserved

#### DynamoDB Tables
- **Jobs-{stage}**: Video generation job tracking
- **Credits-{stage}**: User credit balances
- **Ledger-{stage}**: Complete transaction audit trail

#### Monitoring & Alerts
- **DLQ**: `cc-reconciler-dlq-{stage}` (14-day retention)
- **Error Alarm**: `cc-reconciler-errors-{stage}` (≥1 error in 5 min)
- **Rate Alarm**: `cc-reconciler-adjustments-{stage}` (>100/hour)
- **SNS Topic**: `ops-alerts-{stage}`

## Operations

### Dead Letter Queue Management

#### View Failed Messages
```bash
# List messages in DLQ
aws sqs receive-message --queue-url https://sqs.us-east-1.amazonaws.com/ACCOUNT/cc-reconciler-dlq-prod --max-number-of-messages 10

# Get DLQ attributes
aws sqs get-queue-attributes --queue-url https://sqs.us-east-1.amazonaws.com/ACCOUNT/cc-reconciler-dlq-prod --attribute-names All
```

#### Replay Failed Messages
```bash
# Manual replay from DLQ
aws lambda invoke --function-name cc-agent-reconciler-prod --payload file://failed-event.json response.json

# Batch replay script
for message in $(aws sqs receive-message --queue-url $DLQ_URL --query 'Messages[].Body' --output text); do
    aws lambda invoke --function-name cc-agent-reconciler-prod --payload "$message" /tmp/response.json
    echo "Replayed message: $message"
done
```

### Alarm Management

#### Disable Alarms During Maintenance
```bash
# Disable error alarm
aws cloudwatch disable-alarm-actions --alarm-names cc-reconciler-errors-prod

# Re-enable after maintenance
aws cloudwatch enable-alarm-actions --alarm-names cc-reconciler-errors-prod
```

#### Check Alarm Status
```bash
# View alarm states
aws cloudwatch describe-alarms --alarm-names cc-reconciler-errors-prod cc-reconciler-adjustments-prod

# View alarm history
aws cloudwatch describe-alarm-history --alarm-name cc-reconciler-errors-prod
```

### Monitoring

#### CloudWatch Logs
```bash
# Tail live logs
aws logs tail /aws/lambda/cc-agent-reconciler-prod --follow

# Search for errors
aws logs filter-log-events --log-group-name /aws/lambda/cc-agent-reconciler-prod --filter-pattern "ERROR"

# View specific time range
aws logs filter-log-events --log-group-name /aws/lambda/cc-agent-reconciler-prod --start-time 1640995200000
```

#### Custom Metrics
```bash
# View adjustment metrics
aws cloudwatch get-metric-statistics --namespace Reconciler --metric-name Adjustments --start-time 2025-06-21T00:00:00Z --end-time 2025-06-21T23:59:59Z --period 3600 --statistics Sum

# Lambda metrics
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Errors --dimensions Name=FunctionName,Value=cc-agent-reconciler-prod --start-time 2025-06-21T00:00:00Z --end-time 2025-06-21T23:59:59Z --period 300 --statistics Sum
```

### Database Operations

#### Query User Credits
```bash
# Check user balance
aws dynamodb get-item --table-name Credits-prod --key '{"userId": {"S": "user123"}}'

# Scan recent ledger entries
aws dynamodb scan --table-name Ledger-prod --filter-expression "contains(#ts, :date)" --expression-attribute-names '{"#ts": "timestamp"}' --expression-attribute-values '{":date": {"S": "2025-06-21"}}'
```

#### Emergency Credit Adjustment
```bash
# Manual credit adjustment (emergency only)
aws dynamodb update-item --table-name Credits-prod --key '{"userId": {"S": "user123"}}' --update-expression "SET remaining = remaining + :amount" --expression-attribute-values '{":amount": {"N": "10"}}'

# Log manual adjustment in ledger
aws dynamodb put-item --table-name Ledger-prod --item '{
    "ledgerId": {"S": "manual-adj-'$(date +%s)'"},
    "userId": {"S": "user123"},
    "timestamp": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)'"},
    "type": {"S": "credit"},
    "amount": {"N": "10"},
    "description": {"S": "Manual emergency adjustment"},
    "reference": {"S": "MANUAL-'$(date +%s)'"}
}'
```

## Testing

### Smoke Test
```bash
# Test development environment
python scripts/smoke-test.py --env dev

# Test production environment  
python scripts/smoke-test.py --env prod
```

### Manual Testing
```bash
# Publish test event
aws events put-events --entries '[{
    "Source": "video.generation",
    "DetailType": "video.rendered", 
    "Detail": "{\"jobId\": \"test-123\", \"userId\": \"test-user\", \"seconds\": 5, \"model\": \"test\"}"
}]'

# Check processing results
aws dynamodb get-item --table-name Credits-prod --key '{"userId": {"S": "test-user"}}'
```

## Security

### IAM Permissions
The Lambda function uses least-privilege IAM policies:
- **DynamoDB**: CRUD access to Credits, Jobs, Ledger tables only
- **SQS**: Send message to DLQ only
- **SNS**: Publish to ops-alerts topic only
- **Secrets Manager**: Read meta-agents/openai secret only
- **CloudWatch**: Metrics and logs write access

### Secret Management
- OpenAI API key stored in AWS Secrets Manager
- Retrieved at runtime with caching
- No secrets in environment variables or code

## Troubleshooting

### Common Issues

#### High Error Rate
1. Check CloudWatch alarm: `cc-reconciler-errors-prod`
2. Review Lambda logs for error patterns
3. Check DLQ for failed events
4. Verify DynamoDB table capacity and throttling

#### Credit Discrepancies  
1. Query ledger table for audit trail
2. Compare job status vs reconciliation status
3. Run manual timer scan if needed
4. Check for duplicate processing

#### Missing Events
1. Verify EventBridge rule configuration
2. Check event source integration
3. Review timer scan logs for catch-up processing
4. Validate event payload structure

### Emergency Procedures

#### Service Degradation
1. Disable EventBridge rules to stop new processing
2. Scale down Lambda concurrency if needed
3. Investigate root cause via logs and metrics
4. Process DLQ backlog after resolution

#### Data Integrity Issues
1. Take DynamoDB backup snapshots
2. Disable processing during investigation
3. Use ledger audit trail to identify discrepancies
4. Apply corrective transactions with full logging

## Performance

### Benchmarks
- **Processing Time**: ~300ms average per event
- **Memory Usage**: ~85MB peak
- **Throughput**: 10 concurrent executions
- **Error Rate**: <0.1% under normal conditions

### Scaling
- **Lambda**: Auto-scales with reserved concurrency limit
- **DynamoDB**: On-demand billing mode
- **SQS**: Unlimited message retention (14 days)

## Version History

### v1.0 (Production Release)
- ✅ Dead Letter Queue integration
- ✅ CloudWatch alarms with SNS notifications  
- ✅ Multi-environment support (dev/staging/prod)
- ✅ AWS Secrets Manager integration
- ✅ Comprehensive monitoring and logging
- ✅ Production hardening and error handling

### Previous Versions
- v0.x: Development and testing phases

## Support

### Alerts
Production errors automatically trigger:
1. CloudWatch alarm: `cc-reconciler-errors-prod`
2. SNS notification to: `ops-alerts-prod`
3. DLQ message for investigation

### Contact
- **Primary**: Development team via ops-alerts SNS topic
- **Escalation**: CloudWatch dashboards and runbooks
- **Documentation**: This README and AWS CloudFormation template