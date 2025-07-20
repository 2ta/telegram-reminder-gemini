#!/usr/bin/env python3
"""
LangSmith MCP Tool

A simplified tool for direct LangSmith access and debugging.
This can be used to analyze traces and provide debugging insights.
"""

import json
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.langsmith_debug_tool import LangSmithDebugTool

def debug_bot_traces(api_key: str, action: str = "recent", **kwargs):
    """
    Debug bot traces using LangSmith.
    
    Args:
        api_key: LangSmith API key
        action: Action to perform (recent, analyze, metrics, search)
        **kwargs: Additional arguments for the action
    
    Returns:
        Dict with debugging information
    """
    tool = LangSmithDebugTool(api_key, "telegram-reminder-bot")
    
    if action == "recent":
        traces = tool.get_recent_traces(kwargs.get('limit', 5))
        return {
            "action": "recent_traces",
            "traces": traces,
            "summary": f"Found {len(traces)} recent traces"
        }
    
    elif action == "analyze" and kwargs.get('trace_id'):
        analysis = tool.analyze_trace(kwargs['trace_id'])
        return {
            "action": "trace_analysis",
            "trace_id": kwargs['trace_id'],
            "analysis": analysis
        }
    
    elif action == "metrics":
        metrics = tool.get_performance_metrics(kwargs.get('hours', 24))
        return {
            "action": "performance_metrics",
            "metrics": metrics
        }
    
    elif action == "search" and kwargs.get('user_id'):
        traces = tool.search_traces_by_user(kwargs['user_id'], kwargs.get('limit', 10))
        return {
            "action": "user_traces",
            "user_id": kwargs['user_id'],
            "traces": traces
        }
    
    else:
        return {
            "error": f"Invalid action: {action} or missing required parameters"
        }

def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 3:
        print("Usage: python langsmith_mcp_tool.py <api_key> <action> [args...]")
        print("Actions: recent, analyze <trace_id>, metrics, search <user_id>")
        sys.exit(1)
    
    api_key = sys.argv[1]
    action = sys.argv[2]
    
    kwargs = {}
    if action == "analyze" and len(sys.argv) >= 4:
        kwargs['trace_id'] = sys.argv[3]
    elif action == "search" and len(sys.argv) >= 4:
        kwargs['user_id'] = sys.argv[3]
    elif action == "recent" and len(sys.argv) >= 4:
        kwargs['limit'] = int(sys.argv[3])
    elif action == "metrics" and len(sys.argv) >= 4:
        kwargs['hours'] = int(sys.argv[3])
    
    result = debug_bot_traces(api_key, action, **kwargs)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main() 