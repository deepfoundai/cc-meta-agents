# DevOps Interface - EventBridge API

The DevOps-Automation Agent provides a centralized, auditable EventBridge-based API for privileged DevOps operations across the ContentCraft ecosystem.

## Overview

Agents can request DevOps operations by publishing `devops.request` events to the default EventBridge bus. The DevOps-Automation Agent processes these requests and publishes `devops.completed` events with results.

## Event Pattern

### Request Event Format

```json
{
  "source": "agent.<AgentName>",
  "detail-type": "devops.request",
  "detail": {
    "requestId": "uuid4-string",
    "action": "putSecret|deployLambda",
    "stage": "dev|prod",
    "params": {
      // action-specific parameters
    },
    "requestedBy": "AgentName",
    "ts": "2025-06-21T12:00:00Z"
  }
}
```

### Response Event Format

```json
{
  "source": "devops.automation",
  "detail-type": "devops.completed",
  "detail": {
    "requestId": "uuid4-string",
    "action": "putSecret|deployLambda",
    "status": "success|error",
    "result": {
      // action-specific result data
    },
    "error": "error message (if status=error)",
    "latencyMs": 250,
    "requestedBy": "AgentName",
    "timestamp": "2025-06-21T12:00:30Z"
  }
}
```

## Supported Actions

### 1. putSecret

Creates or updates secrets in AWS Secrets Manager.

**Parameters:**
- `name` (required): Full secret path (e.g., `/contentcraft/service/api_key`)
- `value` (required): Secret value (JSON string or plaintext)
- `kmsKey` (optional): KMS key ID for encryption

**Example Request:**
```json
{
  "source": "agent.CostSentinel",
  "detail-type": "devops.request",
  "detail": {
    "requestId": "12345678-abcd-1234-efgh-123456789012",
    "action": "putSecret",
    "stage": "prod",
    "params": {
      "name": "/contentcraft/costsent/threshold",
      "value": "{\"spendPct\": 30}",
      "kmsKey": "alias/contentcraft-secrets"
    },
    "requestedBy": "CostSentinel",
    "ts": "2025-06-21T12:00:00Z"
  }
}
```

**Success Response:**
```json
{
  "source": "devops.automation",
  "detail-type": "devops.completed",
  "detail": {
    "requestId": "12345678-abcd-1234-efgh-123456789012",
    "action": "putSecret",
    "status": "success",
    "result": {
      "secretName": "/contentcraft/costsent/threshold",
      "action": "created|updated",
      "arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:/contentcraft/costsent/threshold-AbCdEf",
      "versionId": "version-uuid"
    },
    "latencyMs": 150,
    "requestedBy": "CostSentinel",
    "timestamp": "2025-06-21T12:00:00.150Z"
  }
}
```

### 2. deployLambda

Triggers CloudFormation stack deployment for Lambda functions.

**Parameters:**
- `stackName` (required): CloudFormation stack name (without stage suffix)
- `stage` (optional): Deployment stage (defaults to event-level stage)

**Example Request:**
```json
{
  "source": "agent.DocRegistry",
  "detail-type": "devops.request",
  "detail": {
    "requestId": "87654321-dcba-4321-hgfe-987654321098",
    "action": "deployLambda",
    "stage": "dev",
    "params": {
      "stackName": "cc-agent-doc-registry",
      "stage": "dev"
    },
    "requestedBy": "DocRegistry",
    "ts": "2025-06-21T12:00:00Z"
  }
}
```

**Success Response:**
```json
{
  "source": "devops.automation",
  "detail-type": "devops.completed",
  "detail": {
    "requestId": "87654321-dcba-4321-hgfe-987654321098",
    "action": "deployLambda",
    "status": "success",
    "result": {
      "stackName": "cc-agent-doc-registry-dev",
      "action": "deployment_queued",
      "currentStatus": "UPDATE_COMPLETE",
      "note": "Phase 2 implementation - deployment queued for manual processing"
    },
    "latencyMs": 300,
    "requestedBy": "DocRegistry",
    "timestamp": "2025-06-21T12:00:00.300Z"
  }
}
```

## Error Handling

**Error Response Format:**
```json
{
  "source": "devops.automation",
  "detail-type": "devops.completed",
  "detail": {
    "requestId": "request-uuid",
    "action": "putSecret",
    "status": "error",
    "error": "Failed to create secret /invalid/path: Access denied",
    "latencyMs": 50,
    "requestedBy": "AgentName",
    "timestamp": "2025-06-21T12:00:00.050Z"
  }
}
```

**Common Error Scenarios:**
- Missing required parameters
- Invalid secret paths (must start with `/contentcraft/`)
- CloudFormation stack not found
- Stack in progress state
- Insufficient IAM permissions
- Invalid action type

## Security Considerations

### Access Control
- Only events from sources matching `agent.*` pattern are processed
- Secret operations are restricted to `/contentcraft/*` namespace
- All operations are tagged with `createdBy=DevOpsAutomation`
- CloudFormation operations require stack existence (no creation)

### Audit Trail
- All requests and responses are logged in CloudWatch
- EventBridge events provide complete audit trail
- Request latency is tracked for performance monitoring
- All operations include requesting agent identification

### Resource Isolation
- Stage-specific resource naming
- Environment separation via stage parameters
- KMS encryption support for sensitive secrets

## Integration Examples

### Cost-Sentinel Requesting Secret Update

```python
import boto3
import json
import uuid
from datetime import datetime, timezone

events_client = boto3.client('events')

def update_threshold_secret(new_threshold: float):
    event = {
        'Source': 'agent.CostSentinel',
        'DetailType': 'devops.request',
        'Detail': json.dumps({
            'requestId': str(uuid.uuid4()),
            'action': 'putSecret',
            'stage': 'prod',
            'params': {
                'name': '/contentcraft/costsent/threshold',
                'value': json.dumps({'spendPct': new_threshold})
            },
            'requestedBy': 'CostSentinel',
            'ts': datetime.now(timezone.utc).isoformat()
        })
    }
    
    response = events_client.put_events(Entries=[event])
    return response
```

### Listening for Completion Events

```python
def handle_devops_completion(event, context):
    """Lambda handler for devops.completed events"""
    detail = event['detail']
    
    if detail['status'] == 'success':
        print(f"DevOps operation {detail['action']} completed successfully")
        print(f"Latency: {detail['latencyMs']}ms")
        print(f"Result: {detail['result']}")
    else:
        print(f"DevOps operation failed: {detail['error']}")
        # Handle error case
```

## Testing

### Local Testing with SAM

```bash
# Test putSecret request
sam local invoke DevOpsAutomationFunction \
  --event tests/events/devops_put_secret.json

# Test deployLambda request  
sam local invoke DevOpsAutomationFunction \
  --event tests/events/devops_deploy_lambda.json
```

### End-to-End Testing

1. **Publish Test Event:**
```bash
aws events put-events \
  --entries file://tests/events/devops_put_secret.json
```

2. **Check CloudWatch Logs:**
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/cc-agent-devops-automation-prod \
  --start-time $(date -d '5 minutes ago' +%s)000
```

3. **Verify Secret Creation:**
```bash
aws secretsmanager describe-secret \
  --secret-id /contentcraft/test/devops-secret
```

## Monitoring & Observability

### CloudWatch Metrics
- `Agent/DevOpsAutomation/RequestLatency`: Request processing time
- `Agent/DevOpsAutomation/RequestCount`: Number of requests processed
- `Agent/DevOpsAutomation/ErrorRate`: Percentage of failed requests

### Alarms
- High error rate (>5%)
- High latency (>5000ms)
- Request volume spikes

### Dashboards
- Real-time request processing status
- Agent request distribution
- Success/error rates by action type

## Best Practices

### For Requesting Agents

1. **Use Unique Request IDs**: Always generate UUID4 for traceability
2. **Handle Async Responses**: Listen for `devops.completed` events
3. **Implement Timeouts**: Don't wait indefinitely for responses
4. **Validate Parameters**: Check required fields before sending requests
5. **Handle Errors Gracefully**: Implement retry logic for transient failures

### For Request Patterns

1. **Batch Operations**: Combine related operations when possible
2. **Idempotent Requests**: Design requests to be safely retryable
3. **Resource Naming**: Use consistent, predictable naming conventions
4. **Stage Awareness**: Always specify appropriate stage

## Migration Guide

For agents currently making direct AWS API calls:

1. **Identify Operations**: List current IAM-dependent operations
2. **Create Request Events**: Convert to `devops.request` format
3. **Add Event Handlers**: Implement `devops.completed` listeners
4. **Remove Direct IAM**: Remove unnecessary AWS permissions
5. **Test Integration**: Validate request/response flow

## Roadmap

### Phase 3 Enhancements
- **Branch Protection**: Automated GitHub repository configuration
- **Dependency Management**: Package and security updates
- **Certificate Management**: SSL/TLS certificate automation
- **Monitoring Setup**: CloudWatch dashboard and alarm creation

### Future Actions
- `createStack`: Initial CloudFormation stack creation
- `updateDNS`: Route53 record management
- `rotateCertificate`: Automated certificate renewal
- `patchSecurity`: Automated security update deployment

---

**Documentation Version**: 2.0  
**Last Updated**: 2025-06-21  
**Maintainer**: DevOps-Automation Agent 