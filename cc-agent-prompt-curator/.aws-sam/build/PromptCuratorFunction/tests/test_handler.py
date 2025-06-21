import pytest
import json
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from moto import mock_aws
import boto3

from src.handler import (
    lambda_handler, dedupe_and_score, clean_phrase, calculate_score,
    generate_prompts, create_slug, determine_mood, persist_results,
    emit_invalidation_event, emit_metrics
)

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("DDB_TABLE_NAME", "test-table")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

@pytest.fixture
def sample_phrases():
    return [
        {"source": "twitter", "phrase": "AI revolution"},
        {"source": "tiktok", "phrase": "#AIRevolution"},
        {"source": "google", "phrase": "AI Revolution"},
        {"source": "twitter", "phrase": "climate change"},
        {"source": "tiktok", "phrase": "viral dance"}
    ]

@pytest.fixture
def sample_scored_phrases():
    return [
        {
            "phrase": "ai revolution",
            "count": 3,
            "sources": ["twitter", "tiktok", "google"],
            "score": 15.5
        },
        {
            "phrase": "climate change",
            "count": 1,
            "sources": ["twitter"],
            "score": 8.2
        }
    ]

class TestCleanPhrase:
    def test_clean_phrase_basic(self):
        assert clean_phrase("Hello World!") == "hello world"
    
    def test_clean_phrase_hashtag(self):
        assert clean_phrase("#TrendingNow") == "#trendingnow"
    
    def test_clean_phrase_special_chars(self):
        assert clean_phrase("AI & ML @2024") == "ai ml @2024"
    
    def test_clean_phrase_multiple_spaces(self):
        assert clean_phrase("  multiple   spaces  ") == "multiple spaces"

class TestCalculateScore:
    def test_calculate_score_basic(self):
        score = calculate_score("test phrase", 2, 1)
        assert score > 0
    
    def test_calculate_score_hashtag_bonus(self):
        hashtag_score = calculate_score("#trending", 1, 1)
        regular_score = calculate_score("trending", 1, 1)
        assert hashtag_score > regular_score
    
    def test_calculate_score_multiple_sources(self):
        multi_source_score = calculate_score("test", 1, 3)
        single_source_score = calculate_score("test", 1, 1)
        assert multi_source_score > single_source_score

class TestDedupeAndScore:
    def test_dedupe_and_score(self, sample_phrases):
        result = dedupe_and_score(sample_phrases)
        
        assert len(result) == 4  # ai revolution, #airevolution, climate change, viral dance
        assert result[0]["phrase"] == "ai revolution"
        assert result[0]["count"] == 2  # twitter and google
        assert len(result[0]["sources"]) == 2
        assert result[0]["score"] > result[1]["score"]

class TestCreateSlug:
    def test_create_slug_basic(self):
        assert create_slug("Hello World") == "hello-world"
    
    def test_create_slug_special_chars(self):
        assert create_slug("AI & ML!") == "ai-ml"
    
    def test_create_slug_hashtag(self):
        assert create_slug("#TrendingNow") == "trendingnow"

class TestDetermineMood:
    def test_determine_mood_upbeat(self):
        assert determine_mood("happy celebration") == "upbeat"
    
    def test_determine_mood_dramatic(self):
        assert determine_mood("dark mystery night") == "dramatic"
    
    def test_determine_mood_serene(self):
        assert determine_mood("beautiful sunset ocean") == "serene"
    
    def test_determine_mood_energetic(self):
        assert determine_mood("fast action race") == "energetic"
    
    def test_determine_mood_neutral(self):
        assert determine_mood("random phrase") == "neutral"

class TestGeneratePrompts:
    @patch('src.handler.openai.ChatCompletion.create')
    def test_generate_prompts_success(self, mock_openai, sample_scored_phrases):
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Stunning AI revolution in neon-lit cityscape"
        mock_openai.return_value = mock_response
        
        result = generate_prompts(sample_scored_phrases[:1])
        
        assert len(result) == 1
        assert result[0]["title"] == "ai revolution"
        assert result[0]["slug"] == "ai-revolution"
        assert len(result[0]["prompt_text"]) <= 80
        assert "mood" in result[0]
        assert "score" in result[0]
        assert "sources" in result[0]
    
    @patch('src.handler.openai.ChatCompletion.create')
    def test_generate_prompts_long_response(self, mock_openai, sample_scored_phrases):
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "A" * 100
        mock_openai.return_value = mock_response
        
        result = generate_prompts(sample_scored_phrases[:1])
        
        assert len(result) == 1
        assert len(result[0]["prompt_text"]) == 80
        assert result[0]["prompt_text"].endswith("...")
    
    @patch('src.handler.openai.ChatCompletion.create')
    def test_generate_prompts_api_failure(self, mock_openai, sample_scored_phrases):
        mock_openai.side_effect = Exception("API Error")
        
        result = generate_prompts(sample_scored_phrases)
        
        assert len(result) == 0

@mock_aws
class TestPersistResults:
    def setup_method(self):
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        self.s3 = boto3.client('s3', region_name='us-east-1')
        
        self.table = self.dynamodb.create_table(
            TableName='test-table',
            KeySchema=[
                {'AttributeName': 'date', 'KeyType': 'HASH'},
                {'AttributeName': 'slug', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'date', 'AttributeType': 'S'},
                {'AttributeName': 'slug', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        self.s3.create_bucket(Bucket='test-bucket')
    
    def test_persist_results_success(self):
        prompts = [
            {
                "title": "test prompt",
                "slug": "test-prompt",
                "prompt_text": "Amazing test video",
                "mood": "neutral",
                "score": 10.0,
                "sources": ["twitter"]
            }
        ]
        
        persist_results("2024-01-01", prompts)
        
        response = self.table.get_item(
            Key={'date': '2024-01-01', 'slug': 'test-prompt'}
        )
        assert 'Item' in response
        assert response['Item']['title'] == 'test prompt'
        
        s3_response = self.s3.get_object(Bucket='test-bucket', Key='2024-01-01.json')
        s3_data = json.loads(s3_response['Body'].read())
        assert s3_data['date'] == '2024-01-01'
        assert len(s3_data['prompts']) == 1
        
        latest_response = self.s3.get_object(Bucket='test-bucket', Key='latest.json')
        latest_data = json.loads(latest_response['Body'].read())
        assert latest_data['date'] == '2024-01-01'

@mock_aws
class TestEmitInvalidationEvent:
    def setup_method(self):
        self.events = boto3.client('events', region_name='us-east-1')
    
    @patch('src.handler.events')
    def test_emit_invalidation_event_success(self, mock_events):
        emit_invalidation_event("2024-01-01")
        
        mock_events.put_events.assert_called_once()
        call_args = mock_events.put_events.call_args[1]
        
        assert len(call_args['Entries']) == 1
        entry = call_args['Entries'][0]
        assert entry['Source'] == 'cc.agent.prompt-curator'
        assert entry['DetailType'] == 'prompt.templates.updated'
        
        detail = json.loads(entry['Detail'])
        assert detail['date'] == '2024-01-01'
        assert 's3_url' in detail
        assert 'latest_url' in detail

@mock_aws
class TestEmitMetrics:
    def setup_method(self):
        self.cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
    
    @patch('src.handler.cloudwatch')
    def test_emit_metrics_success(self, mock_cloudwatch):
        start_time = datetime.utcnow()
        emit_metrics(5, start_time)
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args[1]
        
        assert call_args['Namespace'] == 'ContentCraft/PromptCurator'
        assert len(call_args['MetricData']) == 2
        
        metrics = {m['MetricName']: m for m in call_args['MetricData']}
        assert metrics['TemplatesGenerated']['Value'] == 5
        assert metrics['ExecutionDuration']['Value'] > 0

class TestLambdaHandler:
    @patch('src.handler.collect_trending_phrases')
    @patch('src.handler.generate_prompts')
    @patch('src.handler.persist_results')
    @patch('src.handler.emit_invalidation_event')
    @patch('src.handler.emit_metrics')
    def test_lambda_handler_success(self, mock_emit_metrics, mock_emit_event, 
                                  mock_persist, mock_generate, mock_collect):
        mock_collect.return_value = [{"source": "test", "phrase": "test phrase"}]
        mock_generate.return_value = [{"title": "test", "slug": "test"}]
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['status'] == 'success'
        assert 'date' in body
        assert 'generated_count' in body
        
        mock_collect.assert_called_once()
        mock_generate.assert_called_once()
        mock_persist.assert_called_once()
        mock_emit_event.assert_called_once()
        mock_emit_metrics.assert_called_once()
    
    @patch('src.handler.collect_trending_phrases')
    def test_lambda_handler_failure(self, mock_collect):
        mock_collect.side_effect = Exception("Test error")
        
        with pytest.raises(Exception):
            lambda_handler({}, {})
