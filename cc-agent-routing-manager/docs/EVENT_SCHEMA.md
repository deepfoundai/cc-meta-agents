# Event Schema Documentation

## Overview
The Routing-Manager Agent processes `video.job.submitted` events and emits either `video.job.routed` or `video.job.rejected` events based on routing rules.

## Inbound Events

### video.job.submitted
Source: `frontend.api`

#### Schema
```json
{
  "source": "frontend.api",
  "detail-type": "video.job.submitted",
  "detail": {
    "jobId": "string (required) - Unique job identifier",
    "userId": "string (required) - User who submitted the job",
    "prompt": "string (required) - Video generation prompt",
    "lengthSec": "number (optional) - Video length in seconds",
    "resolution": "string (optional) - Video resolution (e.g., '720p', '1080p')",
    "tier": "string (optional) - User tier (e.g., 'standard', 'premium')",
    "provider": "string (optional) - Preferred provider ('auto', 'fal', 'replicate')",
    "feature": {
      "audio": "boolean (optional) - Whether audio is required"
    }
  }
}
```

#### Example
```json
{
  "source": "frontend.api",
  "detail-type": "video.job.submitted",
  "detail": {
    "jobId": "550e8400-e29b-41d4-a716-446655440000",
    "userId": "user-123",
    "prompt": "A corgi surfing on a beach at sunset",
    "lengthSec": 8,
    "resolution": "720p",
    "tier": "standard",
    "provider": "auto"
  }
}
```

## Outbound Events

### video.job.routed
Source: `routing.manager`

Emitted when a job is successfully routed to a provider queue.

#### Schema
```json
{
  "source": "routing.manager",
  "detail-type": "video.job.routed",
  "detail": {
    "jobId": "string - Job identifier",
    "provider": "string - Selected provider (e.g., 'fal', 'replicate')",
    "model": "string - Selected model (e.g., 'wan-i2v')",
    "queue": "string - Target queue name",
    "routedBy": "string - Always 'RoutingManager'",
    "ts": "string - ISO 8601 timestamp"
  }
}
```

#### Example
```json
{
  "source": "routing.manager",
  "detail-type": "video.job.routed",
  "detail": {
    "jobId": "550e8400-e29b-41d4-a716-446655440000",
    "provider": "fal",
    "model": "wan-i2v",
    "queue": "FalJobQueue",
    "routedBy": "RoutingManager",
    "ts": "2025-06-22T00:22:00Z"
  }
}
```

### video.job.rejected
Source: `routing.manager`

Emitted when a job cannot be routed to any provider.

#### Schema
```json
{
  "source": "routing.manager",
  "detail-type": "video.job.rejected",
  "detail": {
    "jobId": "string - Job identifier",
    "status": "string - Always 'rejected'",
    "reason": "string - Rejection reason code",
    "ts": "string - ISO 8601 timestamp"
  }
}
```

#### Rejection Reasons
- `no_route` - No routing rule matches the job parameters
- `missing_required_field:{field}` - Required field is missing
- `invalid_length:must_be_1-300_seconds` - Video length out of range
- `invalid_length:not_a_number` - Length is not a valid number
- `unsupported_provider:{provider}` - Specified provider not supported
- `queue_not_configured:{provider}` - Provider queue URL not configured
- `queue_error:{error}` - Failed to send message to SQS queue
- `rule_error:{error}` - Error evaluating routing rules

#### Example
```json
{
  "source": "routing.manager",
  "detail-type": "video.job.rejected",
  "detail": {
    "jobId": "550e8400-e29b-41d4-a716-446655440000",
    "status": "rejected",
    "reason": "no_route",
    "ts": "2025-06-22T00:22:01Z"
  }
}
```

## DynamoDB Records

### Jobs Table Update
When routing a job, the following fields are updated in the `Jobs-{Stage}` table:

```json
{
  "jobId": "string (partition key)",
  "status": "ROUTED",
  "provider": "string - Selected provider",
  "model": "string - Selected model",
  "routedAt": "string - ISO 8601 timestamp",
  "routedBy": "RoutingManager",
  "queue": "string - Queue name (without full URL)"
}
```

For rejected jobs:
```json
{
  "jobId": "string (partition key)",
  "status": "REJECTED",
  "rejectionReason": "string - Reason code",
  "rejectedAt": "string - ISO 8601 timestamp"
}
```

## SQS Message Format

Messages sent to provider queues contain the original job data with these message attributes:

### Message Body
The complete original `video.job.submitted` event detail

### Message Attributes
- `provider` (String) - Selected provider
- `model` (String) - Selected model
- `jobId` (String) - Job identifier