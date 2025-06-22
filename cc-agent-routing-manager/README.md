# Routing-Manager Agent (AGENT-06)

Central dispatcher for video-generation jobs. Routes `video.job.submitted` events to appropriate backend providers (fal.ai, Replicate, etc.) based on job requirements and static rules.

## Phase-1 Scope (MVP)

### Features
1. **Rule Engine** - Static routing rules based on video parameters
2. **Idempotent Processing** - Deduplicates jobs by jobId
3. **Event-Driven** - Consumes EventBridge events, emits routing decisions
4. **Heartbeat Monitoring** - Regular health metric publishing
5. **SQS Integration** - Routes jobs to provider-specific queues

### Routing Rules (MVP)
- `≤10s & 720p` → provider=`fal`, model=`wan-i2v`
- Explicit provider specified → respect it
- Otherwise → reject with reason `"no_route"`

## Architecture

```
EventBridge (video.job.submitted) → Lambda → DynamoDB (Jobs-{Stage})
                                         ↓
                                    SQS Queues (FalJobQueue, ReplicateJobQueue)
                                         ↓
                                    EventBridge (video.job.routed/rejected)
```

## Event Schemas

### Input: video.job.submitted
```json
{
  "jobId": "uuid",
  "userId": "user-123",
  "prompt": "corgi surfing",
  "lengthSec": 8,
  "resolution": "720p",
  "tier": "standard",
  "provider": "auto"  // or "fal"|"replicate"
}
```

### Output: video.job.routed
```json
{
  "jobId": "uuid",
  "provider": "fal",
  "model": "wan-i2v",
  "queue": "FalJobQueue",
  "routedBy": "RoutingManager",
  "ts": "2025-06-22T00:22:00Z"
}
```

### Output: video.job.rejected
```json
{
  "jobId": "uuid",
  "status": "rejected",
  "reason": "no_route",
  "ts": "2025-06-22T00:22:01Z"
}
```

## Deployment

### Prerequisites
- AWS SAM CLI
- Python 3.12
- Access to DynamoDB table `Jobs-{Stage}`
- SQS queues: `FalJobQueue`, `ReplicateJobQueue`

### Deploy
```bash
# Build and deploy
sam build
sam deploy --config-env dev \
  --parameter-overrides \
  FalQueueUrl=https://sqs.region.amazonaws.com/account/FalJobQueue \
  ReplicateQueueUrl=https://sqs.region.amazonaws.com/account/ReplicateJobQueue

# Validate deployment
sam validate
```

## Testing

### Unit Tests
```bash
# Run tests with coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Integration Test
```bash
# Send test event
aws events put-events --entries file://tests/events/sample_video_job.json

# Check CloudWatch Logs
aws logs tail /aws/lambda/routing-manager --follow
```

### Local Testing
```bash
# Start SAM local
sam local start-lambda

# Invoke with test event
sam local invoke RoutingManagerFunction -e tests/events/sample_video_job.json
```

## Monitoring

### CloudWatch Metrics
- **Namespace**: `VideoJobRouting`
- **Metrics**:
  - `RoutingAttempts` - Count of routing attempts by provider/success
  - `Agent/RoutingManager/Heartbeat` - Health heartbeat every 5 min

### CloudWatch Alarms
- `no-routing` - Triggers when no jobs processed for 10 minutes
- `high-rejection-rate` - Triggers when >10 rejections in 5 minutes

### Logs
```bash
# View recent logs
aws logs tail /aws/lambda/routing-manager-routing-manager --follow

# Search for specific job
aws logs filter-log-events \
  --log-group-name /aws/lambda/routing-manager-routing-manager \
  --filter-pattern '"jobId":"uuid-here"'
```

## Troubleshooting

### Common Issues

1. **Job Already Routed**
   - Check DynamoDB Jobs table for existing status
   - Lambda is idempotent, safe to retry

2. **Queue Not Configured**
   - Verify queue URLs in environment variables
   - Check IAM permissions for SQS SendMessage

3. **No Route Found**
   - Review job parameters against routing rules
   - Check if provider is explicitly specified

4. **Heartbeat Missing**
   - Check EventBridge schedule rule is enabled
   - Verify CloudWatch PutMetricData permissions

## Development

### Project Structure
```
cc-agent-routing-manager/
├── src/
│   ├── handler.py      # Main Lambda handler
│   ├── rules.py        # Routing rule engine
│   └── requirements.txt
├── tests/
│   ├── test_handler.py
│   ├── test_rules.py
│   └── events/
│       └── sample_video_job.json
├── template.yaml       # SAM template
└── README.md
```

### Adding New Providers
1. Update `RoutingRuleEngine.supported_providers` in `rules.py`
2. Add queue URL parameter in `template.yaml`
3. Update queue mapping in `handler.py`
4. Add routing rules as needed

## Future Enhancements (Phase 2+)
- Dynamic routing based on provider availability
- Cost-based routing optimization
- ML-based quality prediction for routing
- Multi-region provider support
- Batch job processing