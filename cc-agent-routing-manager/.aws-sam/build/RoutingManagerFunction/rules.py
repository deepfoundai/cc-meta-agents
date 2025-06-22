"""
Rule Engine for Video Job Routing
Phase-1 MVP implementation with static rules
"""
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger()

class RoutingRuleEngine:
    """Static rule engine for video job routing decisions"""
    
    def __init__(self):
        self.supported_providers = ["fal", "replicate", "veo"]
        self.default_models = {
            "fal": "wan-i2v",
            "replicate": "stable-video",
            "veo": "veo-standard"
        }
    
    def evaluate(self, job: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Evaluate routing rules for a video job
        
        Args:
            job: Video job request with tier, lengthSec, resolution, provider fields
            
        Returns:
            Tuple of (provider, model, rejection_reason)
            - If routable: (provider, model, None)
            - If rejected: (None, None, reason)
        """
        try:
            # Extract job parameters
            tier = job.get("tier", "standard")
            length_sec = int(job.get("lengthSec", 0))
            resolution = job.get("resolution", "720p")
            provider_pref = job.get("provider", "auto")
            
            # Rule 1: If provider explicitly specified, respect it
            if provider_pref != "auto":
                if provider_pref in self.supported_providers:
                    model = self.default_models.get(provider_pref)
                    logger.info(f"Using explicit provider: {provider_pref}, model: {model}")
                    return provider_pref, model, None
                else:
                    logger.warning(f"Unsupported provider requested: {provider_pref}")
                    return None, None, f"unsupported_provider:{provider_pref}"
            
            # Rule 2: ≤10s & 720p → fal with wan-i2v model
            if length_sec <= 10 and resolution == "720p":
                logger.info(f"Routing to fal (wan-i2v) for {length_sec}s {resolution} video")
                return "fal", "wan-i2v", None
            
            # Rule 3: No matching route
            logger.info(f"No route found for {length_sec}s {resolution} video")
            return None, None, "no_route"
            
        except Exception as e:
            logger.error(f"Rule evaluation error: {str(e)}", exc_info=True)
            return None, None, f"rule_error:{str(e)}"
    
    def validate_job(self, job: Dict[str, Any]) -> Optional[str]:
        """
        Validate job has required fields
        
        Returns:
            None if valid, error message if invalid
        """
        required_fields = ["jobId", "userId", "prompt"]
        
        for field in required_fields:
            if field not in job:
                return f"missing_required_field:{field}"
        
        # Validate numeric fields
        try:
            if "lengthSec" in job:
                length = int(job["lengthSec"])
                if length <= 0 or length > 300:  # Max 5 minutes
                    return "invalid_length:must_be_1-300_seconds"
        except (ValueError, TypeError):
            return "invalid_length:not_a_number"
        
        return None