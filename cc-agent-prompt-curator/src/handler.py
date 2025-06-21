import os
import json
import logging
import boto3
import asyncio
import re
from datetime import datetime
from typing import List, Dict, Any
from collections import Counter
import openai
from pythonjsonlogger import jsonlogger

from .sources.trends_scrapers import TrendsScraper

logger = logging.getLogger()
logger.setLevel(logging.INFO)
if logger.handlers:
    for handler in logger.handlers:
        handler.setFormatter(jsonlogger.JsonFormatter())

ddb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
events = boto3.client("events")
cloudwatch = boto3.client("cloudwatch")

TABLE_NAME = os.environ.get("DDB_TABLE_NAME")
BUCKET = os.environ.get("S3_BUCKET")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4")
openai.api_key = os.environ.get("OPENAI_API_KEY")

def lambda_handler(event, context):
    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_time = datetime.utcnow()
    
    try:
        logger.info("Starting prompt curation run", extra={"run_date": run_date, "model": LLM_MODEL})
        
        phrases = asyncio.run(collect_trending_phrases())
        logger.info("Collected trending phrases", extra={"count": len(phrases)})
        
        scored = dedupe_and_score(phrases)
        logger.info("Deduped and scored phrases", extra={"unique_count": len(scored)})
        
        prompts = generate_prompts(scored[:10])
        logger.info("Generated prompts", extra={"prompt_count": len(prompts)})
        
        persist_results(run_date, prompts)
        logger.info("Persisted results", extra={"run_date": run_date})
        
        emit_invalidation_event(run_date)
        logger.info("Emitted cache invalidation event", extra={"run_date": run_date})
        
        emit_metrics(len(prompts), start_time)
        
        logger.info("Prompt curation run completed successfully", extra={
            "run_date": run_date,
            "generated_count": len(prompts),
            "took_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000)
        })
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "date": run_date,
                "generated_count": len(prompts)
            })
        }
        
    except Exception as e:
        logger.exception("Prompt curation run failed", extra={
            "run_date": run_date,
            "error": str(e),
            "took_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000)
        })
        raise

async def collect_trending_phrases() -> List[Dict[str, str]]:
    async with TrendsScraper() as scraper:
        return await scraper.collect_all_trends()

def dedupe_and_score(phrases: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    phrase_counts = Counter()
    phrase_sources = {}
    
    for item in phrases:
        phrase = clean_phrase(item["phrase"])
        if phrase and len(phrase) > 2:
            phrase_counts[phrase] += 1
            if phrase not in phrase_sources:
                phrase_sources[phrase] = set()
            phrase_sources[phrase].add(item["source"])
    
    scored = []
    for phrase, count in phrase_counts.items():
        score = calculate_score(phrase, count, len(phrase_sources[phrase]))
        scored.append({
            "phrase": phrase,
            "count": count,
            "sources": list(phrase_sources[phrase]),
            "score": score
        })
    
    return sorted(scored, key=lambda x: x["score"], reverse=True)

def clean_phrase(phrase: str) -> str:
    phrase = re.sub(r'[^\w\s#@-]', '', phrase)
    phrase = re.sub(r'\s+', ' ', phrase).strip()
    return phrase.lower()

def calculate_score(phrase: str, count: int, source_count: int) -> float:
    length_bonus = min(len(phrase) / 20.0, 1.0)
    frequency_score = count * 2
    diversity_bonus = source_count * 3
    
    if phrase.startswith('#'):
        hashtag_bonus = 2
    else:
        hashtag_bonus = 0
    
    return frequency_score + diversity_bonus + length_bonus + hashtag_bonus

def generate_prompts(scored_phrases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prompts = []
    
    for item in scored_phrases:
        phrase = item["phrase"]
        try:
            system_prompt = "You are a viral-video copywriter specializing in creating engaging text-to-video prompts."
            user_prompt = f"""Create a SHORT, vivid text prompt (≤80 characters) suitable for an 8-second 720p AI video based on this trending topic: "{phrase}"

Include cinematic cues and make it visually compelling. Return only the prompt text, nothing else."""

            response = openai.ChatCompletion.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=50,
                temperature=0.7
            )
            
            prompt_text = response.choices[0].message.content.strip()
            if len(prompt_text) > 80:
                prompt_text = prompt_text[:77] + "..."
            
            slug = create_slug(phrase)
            mood = determine_mood(phrase)
            
            prompts.append({
                "title": phrase,
                "slug": slug,
                "prompt_text": prompt_text,
                "mood": mood,
                "score": item["score"],
                "sources": item["sources"]
            })
            
            logger.info("Generated prompt", extra={"phrase": phrase, "prompt_length": len(prompt_text)})
            
        except Exception as e:
            logger.error("Failed to generate prompt", extra={"phrase": phrase, "error": str(e)})
            continue
    
    return prompts

def create_slug(phrase: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', phrase.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

def determine_mood(phrase: str) -> str:
    phrase_lower = phrase.lower()
    
    if any(word in phrase_lower for word in ['happy', 'joy', 'celebration', 'party', 'fun']):
        return 'upbeat'
    elif any(word in phrase_lower for word in ['dark', 'mystery', 'night', 'shadow']):
        return 'dramatic'
    elif any(word in phrase_lower for word in ['nature', 'sunset', 'ocean', 'mountain']):
        return 'serene'
    elif any(word in phrase_lower for word in ['action', 'fast', 'speed', 'race']):
        return 'energetic'
    else:
        return 'neutral'

def persist_results(run_date: str, prompts: List[Dict[str, Any]]):
    table = ddb.Table(TABLE_NAME)
    
    for prompt in prompts:
        try:
            table.put_item(
                Item={
                    "date": run_date,
                    "slug": prompt["slug"],
                    "title": prompt["title"],
                    "prompt_text": prompt["prompt_text"],
                    "mood": prompt["mood"],
                    "score": prompt["score"],
                    "sources": prompt["sources"],
                    "created_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error("Failed to save prompt to DynamoDB", extra={"slug": prompt["slug"], "error": str(e)})
    
    s3_key_dated = f"{run_date}.json"
    s3_key_latest = "latest.json"
    
    s3_data = {
        "date": run_date,
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(prompts),
        "prompts": prompts
    }
    
    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=s3_key_dated,
            Body=json.dumps(s3_data, indent=2),
            ContentType="application/json"
        )
        
        s3.put_object(
            Bucket=BUCKET,
            Key=s3_key_latest,
            Body=json.dumps(s3_data, indent=2),
            ContentType="application/json"
        )
        
        logger.info("Uploaded to S3", extra={"bucket": BUCKET, "keys": [s3_key_dated, s3_key_latest]})
        
    except Exception as e:
        logger.error("Failed to upload to S3", extra={"bucket": BUCKET, "error": str(e)})
        raise

def emit_invalidation_event(run_date: str):
    try:
        events.put_events(
            Entries=[
                {
                    "Source": "cc.agent.prompt-curator",
                    "DetailType": "prompt.templates.updated",
                    "Detail": json.dumps({
                        "date": run_date,
                        "s3_url": f"s3://{BUCKET}/{run_date}.json",
                        "latest_url": f"s3://{BUCKET}/latest.json"
                    })
                }
            ]
        )
        logger.info("Emitted cache invalidation event", extra={"date": run_date})
    except Exception as e:
        logger.error("Failed to emit invalidation event", extra={"error": str(e)})

def emit_metrics(prompt_count: int, start_time: datetime):
    try:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        cloudwatch.put_metric_data(
            Namespace='ContentCraft/PromptCurator',
            MetricData=[
                {
                    'MetricName': 'TemplatesGenerated',
                    'Value': prompt_count,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'ExecutionDuration',
                    'Value': duration_ms,
                    'Unit': 'Milliseconds'
                }
            ]
        )
        logger.info("Emitted CloudWatch metrics", extra={"templates": prompt_count, "duration_ms": duration_ms})
    except Exception as e:
        logger.error("Failed to emit metrics", extra={"error": str(e)})
