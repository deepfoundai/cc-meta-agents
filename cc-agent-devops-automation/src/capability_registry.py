"""
DevOpsAutomation Capability Registry

Maps action names to their corresponding handler functions.
This registry is used by the request router to dispatch work orders
to the appropriate capability handlers.
"""

from typing import Dict, Callable, Any

# Use dynamic imports to avoid relative import issues
def _get_deploy_stack_handler():
    from handlers.deploy_stack import handle_deploy_stack
    return handle_deploy_stack

def _get_bootstrap_repo_secrets_handler():
    from handlers.bootstrap_repo_secrets import handle_bootstrap_repo_secrets
    return handle_bootstrap_repo_secrets

# Action name to handler function mapping
REGISTRY: Dict[str, str] = {
    "deploy_stack": "_get_deploy_stack_handler",
    "bootstrap_repo_secrets": "_get_bootstrap_repo_secrets_handler",
    # Legacy actions from existing request_router.py
    "putSecret": "handle_put_secret",  # Will be imported from request_router
    "deployLambda": "handle_deploy_lambda",  # Will be imported from request_router
}

def get_handler(action: str) -> Callable:
    """
    Get the handler function for a given action.
    
    Args:
        action: The action name to look up
        
    Returns:
        The handler function for the action
        
    Raises:
        KeyError: If the action is not supported
    """
    if action not in REGISTRY:
        raise KeyError(f"Unsupported action: {action}")
    
    handler_name = REGISTRY[action]
    
    # Handle different handler types
    if handler_name.startswith('_get_'):
        # New structured handlers via factory functions
        return globals()[handler_name]()
    else:
        # Legacy handlers from request_router
        import request_router
        return getattr(request_router, handler_name)

def list_capabilities() -> list:
    """
    Return a list of all supported action names.
    
    Returns:
        List of supported action names
    """
    return list(REGISTRY.keys())

def validate_action(action: str) -> bool:
    """
    Check if an action is supported.
    
    Args:
        action: The action name to validate
        
    Returns:
        True if the action is supported, False otherwise
    """
    return action in REGISTRY 