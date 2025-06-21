# Credit Reconciler Hardening Tasks

## Status: v0.9 - Core functionality complete, needs production hardening

### Current Status Check

| Area                  | OK?          | Comment                                                |
| --------------------- | ------------ | ------------------------------------------------------ |
| **Event handling**    | ✅            | `video.rendered` ➜ debit, `video.failed` ➜ refund.     |
| **Idempotency**       | ✅            | Duplicate events ignored.                              |
| **Timer scan**        | ✅            | 6-hour sweep finds stragglers.                         |
| **Observability**     | ✅            | Logs & metrics present.                                |
| **OpenAI summarizer** | ❌ (disabled) | Only affects "nice" log summaries—no business impact.  |
| **DLQ / Alarm**       | 🚫           | No DLQ or CloudWatch Alarm yet.                        |
| **Prod stack**        | 🚫           | Running only in *-dev* stack; not deployed to *-prod*. |

## Hardening Tasks (Park for Later)

### Task: Production Hardening & Deploy

**Priority**: Low (can be done in parallel with other agent development)

#### 1. Add Dead Letter Queue (DLQ)
- [ ] Add DLQ configuration to EventBridge targets
- [ ] Configure retry policy: 3 attempts before DLQ
- [ ] Add DLQ monitoring alarm

#### 2. Add CloudWatch Alarms
- [ ] Create alarm for Lambda errors: ≥1 in 5 minutes
- [ ] Create SNS topic "ops-alerts" for notifications
- [ ] Add alarm for DLQ messages > 0

#### 3. Parameterize Stack for Multi-Environment
- [ ] Add parameters for:
  - Stage (dev/staging/prod)
  - Table suffix (_dev, _staging, _prod)
  - Event bus name
- [ ] Update all resource references to use parameters

#### 4. Deploy Production Stack
- [ ] Deploy `cc-agent-reconciler-prod` stack
- [ ] Verify prod tables are created
- [ ] Test prod event flow

#### 5. Documentation
- [ ] Add "Operations" section to README.md
- [ ] Document DLQ replay procedure
- [ ] Add runbook for common issues

### Definition of Done
- ✔ DLQ visible in AWS console
- ✔ Alarm triggers when forcing a failure (e.g., throw Exception)
- ✔ Prod stack using *_prod tables & bus
- ✔ Operations documentation complete

### Implementation Notes

#### DLQ Configuration Example
```yaml
DeadLetterQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: !Sub cc-agent-reconciler-dlq-${Environment}
    MessageRetentionPeriod: 1209600  # 14 days

# In EventBridge Rule target:
Targets:
  - Arn: !GetAtt ReconcilerFunction.Arn
    RetryPolicy:
      MaximumRetryAttempts: 3
    DeadLetterConfig:
      Arn: !GetAtt DeadLetterQueue.Arn
```

#### Alarm Configuration Example
```yaml
ErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: !Sub cc-agent-reconciler-errors-${Environment}
    MetricName: Errors
    Namespace: AWS/Lambda
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 1
    AlarmActions:
      - !Ref OpsAlertsTopic
```

## Next Steps

1. **Tag current version**: v0.9-dev-complete
2. **Start FalInvoker agent** in parallel (higher priority)
3. **Return to hardening** during stability sprint

---

**Note**: These hardening tasks are important for production readiness but don't block other agent development. The core reconciliation logic is proven and working.