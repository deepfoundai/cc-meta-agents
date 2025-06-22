############################################################
#  Routing-Manager Agent  (internal codename: AGENT-06)    #
############################################################
Role  
• You are the **central dispatcher** for video-generation jobs.  
• For every `video.job.submitted` event you decide which backend (fal.ai, Replicate, Veo, etc.) should fulfil the request, enqueue it, and emit a routing event.

Existing ecosystem (read-only context)  
• AWS EventBridge default bus (domain event backbone)  
• DynamoDB tables: `Jobs-{Stage}`, `Credits-{Stage}`  
• Active agents:  
  – CreditReconciler  (AGENT-01)  
  – FalInvoker         (AGENT-04) — consumes FalJobQueue  
  – Cost-Sentinel      (AGENT-05)  
  – DevOps-Automation  (AGENT-00) — provides `devops.request` API (putSecret, deployLambda)  
• Admin Dashboard auto-discovers agents via `Agent/<Name>/Heartbeat`.

-----------------------------------------------------------------
Phase-1 Scope   (aim: 2–3 dev-days, MVP routing)
-----------------------------------------------------------------
1. **Rule engine** (`src/rules.py`)
   *Inputs:* `tier`, `lengthSec`, `resolution`, `feature.audio`, credit balance.  
   *Static rules (MVP)*  
     – `≤10 s & 720p` → provider =`fal` model =`wan-i2v`  
     – `provider` specified explicitly → respect it  
     – otherwise emit `video.job.rejected` with reason `"no_route"`.
2. **Router Lambda** (`src/handler.py`)  
   – Deduplicate by `jobId` (idempotent).  
   – Write small routing record to `Jobs-{Stage}` (status =`ROUTED`).  
   – Send the job JSON to **provider SQS queue** (`FalJobQueue` or `ReplicateJobQueue`).  
   – Emit `video.job.routed` (or `video.job.rejected`) on EventBridge.
3. **Heartbeat**  
   – Publish `Agent/RoutingManager/Heartbeat Value=1` every 5 min.
4. **Infrastructure** (`template.yaml`)  
   – Python 3.12 Lambda, 256 MB, 30 s timeout.  
   – SQS queue ARNs passed via `FalQueueUrl` / `ReplicateQueueUrl` parameters.  
   – IAM: `dynamodb:GetItem`, `dynamodb:PutItem`, `sqs:SendMessage`, `events:PutEvents`.
5. **Tests** (`tests/`)  
   – Unit tests for rule engine, idempotency.  
   – SAM local event test for routed vs rejected.  
   – ≥80 % coverage.
6. **Docs**  
   – `README.md` with quick start, event samples, routing logic.  
   – `docs/EVENT_SCHEMA.md` describing `video.job.routed`.

-----------------------------------------------------------------
Event formats
-----------------------------------------------------------------
```jsonc
// Inbound  (source: "frontend.api")
{
  "jobId": "uuid",
  "userId": "user-123",
  "prompt": "corgi surfing",
  "lengthSec": 8,
  "resolution": "720p",
  "tier": "standard",
  "provider": "auto"          // or "fal"|"replicate"
}

// Outbound success  (source: "routing.manager")
{
  "jobId": "uuid",
  "provider": "fal",
  "model": "wan-i2v",
  "queue":  "FalJobQueue",
  "routedBy": "RoutingManager",
  "ts": "2025-06-22T00:22:00Z"
}

// Outbound rejection
{
  "jobId": "uuid",
  "status": "rejected",
  "reason": "no_route",
  "ts": "2025-06-22T00:22:01Z"
}
```

-----------------------------------------------------------------
Definition-of-Done
-----------------------------------------------------------------
✔ `sam validate` passes.
✔ `sam build && sam deploy --config-env dev` succeeds.
✔ Publishing a sample `video.job.submitted` produces a `video.job.routed` record (CloudWatch).
✔ Dashboard shows **RoutingManager** as Healthy (heartbeat metric).
✔ Unit tests ≥ 80 % coverage; integration test JSON files committed.

#################################################################