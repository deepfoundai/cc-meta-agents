"""
Unit tests for the DevOpsAutomation capability registry
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from capability_registry import (
    get_handler, validate_action, list_capabilities, REGISTRY
)


class TestCapabilityRegistry:
    
    def test_list_capabilities(self):
        """Test that list_capabilities returns all available actions"""
        capabilities = list_capabilities()
        
        assert isinstance(capabilities, list)
        assert 'deploy_stack' in capabilities
        assert 'bootstrap_repo_secrets' in capabilities
        assert 'putSecret' in capabilities
        assert 'deployLambda' in capabilities
    
    def test_validate_action_supported(self):
        """Test validation of supported actions"""
        assert validate_action('deploy_stack') is True
        assert validate_action('bootstrap_repo_secrets') is True
        assert validate_action('putSecret') is True
        assert validate_action('deployLambda') is True
    
    def test_validate_action_unsupported(self):
        """Test validation of unsupported actions"""
        assert validate_action('invalid_action') is False
        assert validate_action('') is False
        assert validate_action(None) is False
    
    def test_get_handler_new_actions(self):
        """Test getting handlers for new structured actions"""
        # Mock the handler modules
        with patch('capability_registry.handle_deploy_stack') as mock_deploy:
            with patch('capability_registry.handle_bootstrap_repo_secrets') as mock_bootstrap:
                deploy_handler = get_handler('deploy_stack')
                bootstrap_handler = get_handler('bootstrap_repo_secrets')
                
                assert callable(deploy_handler)
                assert callable(bootstrap_handler)
    
    def test_get_handler_legacy_actions(self):
        """Test getting handlers for legacy actions via string reference"""
        with patch('request_router.handle_put_secret') as mock_put_secret:
            with patch('request_router.handle_deploy_lambda') as mock_deploy_lambda:
                # Mock the request_router module
                mock_router = MagicMock()
                mock_router.handle_put_secret = mock_put_secret
                mock_router.handle_deploy_lambda = mock_deploy_lambda
                
                with patch('capability_registry.request_router', mock_router):
                    put_secret_handler = get_handler('putSecret')
                    deploy_lambda_handler = get_handler('deployLambda')
                    
                    assert put_secret_handler == mock_put_secret
                    assert deploy_lambda_handler == mock_deploy_lambda
    
    def test_get_handler_unsupported_action(self):
        """Test that unsupported actions raise KeyError"""
        with pytest.raises(KeyError, match="Unsupported action: invalid_action"):
            get_handler('invalid_action')
    
    def test_registry_structure(self):
        """Test that the registry has the expected structure"""
        assert isinstance(REGISTRY, dict)
        assert len(REGISTRY) >= 4  # At least the core actions
        
        # Check that all values are either callables or strings (for legacy)
        for action, handler in REGISTRY.items():
            assert isinstance(action, str)
            assert callable(handler) or isinstance(handler, str) 