"""
Unit tests for routing rule engine
"""
import pytest
from src.rules import RoutingRuleEngine


class TestRoutingRuleEngine:
    """Test routing rule engine logic"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.engine = RoutingRuleEngine()
    
    def test_validate_job_valid(self):
        """Test validation with valid job"""
        job = {
            "jobId": "test-123",
            "userId": "user-456",
            "prompt": "test prompt",
            "lengthSec": 5,
            "resolution": "720p"
        }
        
        assert self.engine.validate_job(job) is None
    
    def test_validate_job_missing_required_field(self):
        """Test validation with missing required fields"""
        job = {
            "userId": "user-456",
            "prompt": "test prompt"
        }
        
        error = self.engine.validate_job(job)
        assert error == "missing_required_field:jobId"
    
    def test_validate_job_invalid_length(self):
        """Test validation with invalid length"""
        job = {
            "jobId": "test-123",
            "userId": "user-456",
            "prompt": "test prompt",
            "lengthSec": 0
        }
        
        error = self.engine.validate_job(job)
        assert error == "invalid_length:must_be_1-300_seconds"
        
        job["lengthSec"] = 301
        error = self.engine.validate_job(job)
        assert error == "invalid_length:must_be_1-300_seconds"
        
        job["lengthSec"] = "not a number"
        error = self.engine.validate_job(job)
        assert error == "invalid_length:not_a_number"
    
    def test_evaluate_10s_720p_to_fal(self):
        """Test rule: ≤10s & 720p → fal with wan-i2v"""
        job = {
            "jobId": "test-123",
            "lengthSec": 8,
            "resolution": "720p",
            "provider": "auto"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert provider == "fal"
        assert model == "wan-i2v"
        assert reason is None
    
    def test_evaluate_explicit_provider(self):
        """Test explicit provider specification"""
        job = {
            "jobId": "test-123",
            "lengthSec": 20,
            "resolution": "1080p",
            "provider": "replicate"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert provider == "replicate"
        assert model == "stable-video"
        assert reason is None
    
    def test_evaluate_unsupported_provider(self):
        """Test unsupported provider"""
        job = {
            "jobId": "test-123",
            "provider": "unknown-provider"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert provider is None
        assert model is None
        assert reason == "unsupported_provider:unknown-provider"
    
    def test_evaluate_no_route(self):
        """Test no matching route"""
        job = {
            "jobId": "test-123",
            "lengthSec": 15,
            "resolution": "1080p",
            "provider": "auto"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert provider is None
        assert model is None
        assert reason == "no_route"
    
    def test_evaluate_edge_cases(self):
        """Test edge cases"""
        # Exactly 10s should route to fal
        job = {
            "jobId": "test-123",
            "lengthSec": 10,
            "resolution": "720p",
            "provider": "auto"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert provider == "fal"
        assert model == "wan-i2v"
        
        # Missing optional fields should not break
        job = {
            "jobId": "test-123",
            "provider": "auto"
        }
        
        provider, model, reason = self.engine.evaluate(job)
        assert reason == "no_route"  # 0 seconds, no resolution