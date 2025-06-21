# Agent-02: Prompt Template Curator

A meta-agent that keeps ContentCraft's prompt library fresh by harvesting trending topics from social media and converting them into high-quality text-to-video prompts.

## Overview

This AWS Lambda function runs daily at 06:00 UTC to:
1. Collect trending phrases from Twitter/X, TikTok, and Google Hot Searches
2. Deduplicate and score trending topics
3. Generate creative ≤80-character text-to-video prompts using OpenAI
4. Store results in DynamoDB and publish JSON to S3
5. Emit cache invalidation events for UI updates

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   EventBridge   │───▶│  Lambda Handler  │───▶│   DynamoDB      │
│  (Daily Cron)   │    │                  │    │ PromptTemplates │
└─────────────────┘    │  5-Phase Algo:   │    └─────────────────┘
                       │  1. Collect      │              │
┌─────────────────┐    │  2. Dedupe       │    ┌─────────────────┐
│ Social Media    │───▶│  3. LLM Generate │───▶│       S3        │
│ APIs/Scrapers   │    │  4. Persist      │    │ cc-prompt-      │
└─────────────────┘    │  5. Invalidate   │    │ templates/      │
                       └──────────────────┘    └─────────────────┘
                                 │
                       ┌─────────────────┐
                       │   EventBridge   │
                       │ Cache Invalidate│
                       └─────────────────┘
```

## Data Sources

### Free/Cheap Sources (Current Implementation)
- **Trends24**: `https://trends24.in/api/trending.json` (no auth required)
- **TikTok**: Public trending feed with desktop user agent
- **Google Trends**: RSS feed `https://trends.google.com/trends/trendingsearches/daily/rss`

### Future Upgrade Paths
- Twitter/X v2 API (when credentials available)
- RapidAPI TikTok Scraper (for higher quotas)
- Official Google Trends API (for advanced queries)

## Algorithm

### Phase 1: Collect Signals
- Fetch top 20 entries from each source
- Handle failures gracefully (continue with available sources)
- Normalize into `{source, phrase}` format

### Phase 2: Deduplicate & Score
- Case-fold and clean phrases
- Score based on:
  - Frequency across sources (2x multiplier)
  - Source diversity (3x multiplier)
  - Length bonus (up to 1.0)
  - Hashtag bonus (+2 for phrases starting with #)
- Keep top 10 unique phrases

### Phase 3: LLM Prompt Generation
- Use OpenAI ChatCompletion API with configurable model
- System prompt: "You are a viral-video copywriter..."
- Generate ≤80 character prompts with cinematic cues
- Determine mood (upbeat, dramatic, serene, energetic, neutral)
- Create URL-friendly slugs

### Phase 4: Persist Results
- Store in DynamoDB with composite key (date, slug)
- Upload to S3 as both dated and latest JSON files
- Include metadata: score, sources, mood, timestamps

### Phase 5: Emit Events
- Send EventBridge event `prompt.templates.updated`
- Include S3 URLs for cache invalidation
- Emit CloudWatch metrics for monitoring

## Configuration

### Environment Variables
- `DDB_TABLE_NAME`: DynamoDB table name
- `S3_BUCKET`: S3 bucket for JSON files
- `LLM_MODEL`: OpenAI model (default: gpt-4)
- `OPENAI_API_KEY`: OpenAI API key
- `AWS_REGION`: AWS region (default: us-east-1)

### SAM Parameters
- `Environment`: Deployment environment (dev/staging/prod)
- `AWSRegion`: AWS region override
- `LLMModel`: OpenAI model selection
- `OpenAIAPIKey`: Secure parameter for API key

## Deployment

### Prerequisites
- AWS CLI configured
- SAM CLI installed
- OpenAI API key

### Deploy Steps
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Build and deploy
sam build
sam deploy --guided

# Or use existing config
sam deploy
```

### Stack Resources
- Lambda function with EventBridge trigger
- DynamoDB table with composite key
- S3 bucket with public read policy
- IAM roles and policies
- CloudWatch log groups

## Monitoring

### CloudWatch Metrics
- `ContentCraft/PromptCurator/TemplatesGenerated`: Count of prompts created
- `ContentCraft/PromptCurator/ExecutionDuration`: Runtime in milliseconds

### Logs
- Structured JSON logging with correlation IDs
- Error tracking for each phase
- Performance metrics and timing

### Alerts
- Lambda errors and timeouts
- DynamoDB throttling
- S3 upload failures
- OpenAI API errors

## API Outputs

### S3 JSON Structure
```json
{
  "date": "2024-01-01",
  "generated_at": "2024-01-01T06:00:00Z",
  "count": 8,
  "prompts": [
    {
      "title": "AI Revolution",
      "slug": "ai-revolution",
      "prompt_text": "Neon-lit cityscape with AI holograms dancing in rain",
      "mood": "dramatic",
      "score": 15.5,
      "sources": ["twitter", "tiktok", "google"]
    }
  ]
}
```

### EventBridge Event
```json
{
  "Source": "cc.agent.prompt-curator",
  "DetailType": "prompt.templates.updated",
  "Detail": {
    "date": "2024-01-01",
    "s3_url": "s3://cc-prompt-templates/2024-01-01.json",
    "latest_url": "s3://cc-prompt-templates/latest.json"
  }
}
```

## Development

### Running Tests
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_handler.py

# Run with verbose output
pytest -v --cov-report=html
```

### Local Development
```bash
# Install dev dependencies
pip install -r requirements.txt

# Set environment variables
export DDB_TABLE_NAME=test-table
export S3_BUCKET=test-bucket
export OPENAI_API_KEY=your-key

# Run handler locally
python -c "from src.handler import lambda_handler; print(lambda_handler({}, {}))"
```

### Adding New Sources
1. Create scraper function in `src/sources/trends_scrapers.py`
2. Add to `collect_all_trends()` method
3. Update tests in `tests/test_trends_scrapers.py`
4. No changes needed to core algorithm

## Cost Estimates

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| Lambda | 1 run/day, 30s avg | ~$0.10 |
| DynamoDB | On-demand, ~30 items/month | <$1.00 |
| S3 | 30 JSON files, 2KB each | ~$0.01 |
| OpenAI API | 300 prompts/month | <$1.00 |
| **Total** | | **~$2.11/month** |

## Security

### IAM Permissions
- Read-only HTTP access to public APIs
- `s3:PutObject` to prompt templates bucket
- `dynamodb:PutItem` and `dynamodb:Query` on PromptTemplates table
- `events:PutEvents` for cache invalidation
- `cloudwatch:PutMetricData` for monitoring

### Data Privacy
- No personal data collected
- Only public trending topics processed
- API keys stored in AWS Parameter Store/Secrets Manager
- S3 bucket has public read for JSON files only

## Troubleshooting

### Common Issues
1. **OpenAI API Errors**: Check API key and model availability
2. **Source Scraping Failures**: Verify URLs and rate limits
3. **DynamoDB Throttling**: Consider provisioned capacity
4. **S3 Upload Errors**: Check bucket permissions and region

### Debug Mode
Set `LOG_LEVEL=DEBUG` for verbose logging including:
- Raw API responses
- Scoring calculations
- LLM prompts and responses
- AWS service calls
