"""
LangSmith configuration and setup for the Telegram Reminder Bot.

This module handles LangSmith integration for monitoring, debugging, and tracing
LangGraph applications and LLM interactions.
"""

import os
import logging
from typing import Optional
from langsmith import Client
from langchain_core.tracers import LangChainTracer
# Try to import LangChainTracerV2, fallback to LangChainTracer if not available
try:
    from langchain_core.tracers.langchain import LangChainTracerV2
    HAS_TRACER_V2 = True
except ImportError:
    LangChainTracerV2 = LangChainTracer
    HAS_TRACER_V2 = False
from config.config import settings

logger = logging.getLogger(__name__)

# Global LangSmith client instance
_langsmith_client: Optional[Client] = None
_langchain_tracer: Optional[LangChainTracer] = None

def setup_langsmith() -> None:
    """
    Initialize LangSmith configuration and tracing.
    
    This function sets up LangSmith environment variables and initializes
    the LangSmith client for tracing and monitoring.
    """
    global _langsmith_client, _langchain_tracer
    
    # Check if LangSmith is configured
    if not settings.LANGSMITH_API_KEY:
        logger.info("LangSmith API key not configured. LangSmith tracing will be disabled.")
        return
    
    try:
        # Set LangSmith environment variables
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_TRACING_V2"] = str(settings.LANGSMITH_TRACING_V2).lower()
        
        if settings.LANGSMITH_PROJECT:
            os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
        
        if settings.LANGSMITH_ENDPOINT:
            os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
        
        # Initialize LangSmith client
        _langsmith_client = Client(
            api_key=settings.LANGSMITH_API_KEY,
            api_url=settings.LANGSMITH_ENDPOINT
        )
        
        # Initialize LangChain tracer
        if settings.LANGSMITH_TRACING_V2 and HAS_TRACER_V2:
            _langchain_tracer = LangChainTracerV2(
                project_name=settings.LANGSMITH_PROJECT or "telegram-reminder-bot"
            )
        else:
            _langchain_tracer = LangChainTracer(
                project_name=settings.LANGSMITH_PROJECT or "telegram-reminder-bot"
            )
        
        logger.info(f"LangSmith initialized successfully. Project: {settings.LANGSMITH_PROJECT or 'telegram-reminder-bot'}")
        
    except Exception as e:
        logger.error(f"Failed to initialize LangSmith: {e}", exc_info=True)
        _langsmith_client = None
        _langchain_tracer = None

def get_langsmith_client() -> Optional[Client]:
    """Get the LangSmith client instance."""
    return _langsmith_client

def get_langchain_tracer() -> Optional[LangChainTracer]:
    """Get the LangChain tracer instance."""
    return _langchain_tracer

def is_langsmith_enabled() -> bool:
    """Check if LangSmith is properly configured and enabled."""
    return _langsmith_client is not None and _langchain_tracer is not None

def create_run_name(user_id: str, intent: str = None) -> str:
    """
    Create a descriptive run name for LangSmith tracing.
    
    Args:
        user_id: The Telegram user ID
        intent: The detected intent (optional)
        
    Returns:
        A descriptive run name for the trace
    """
    if intent:
        return f"telegram-bot-{user_id}-{intent}"
    return f"telegram-bot-{user_id}"

def log_graph_execution(user_id: str, node_name: str, state_data: dict = None) -> None:
    """
    Log graph execution information to LangSmith.
    
    Args:
        user_id: The Telegram user ID
        node_name: The name of the current graph node
        state_data: Optional state data to log
    """
    if not is_langsmith_enabled():
        return
    
    try:
        # This would be used in conjunction with LangGraph's built-in tracing
        # The actual tracing is handled automatically by LangGraph when LangSmith is configured
        logger.debug(f"LangSmith tracing active for user {user_id} at node {node_name}")
        
    except Exception as e:
        logger.error(f"Failed to log graph execution to LangSmith: {e}", exc_info=True)

# Initialize LangSmith on module import
setup_langsmith() 