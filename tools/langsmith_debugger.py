"""
LangSmith Debugger Tool

This tool provides automatic access to LangSmith traces for debugging the Telegram bot.
It's designed to be automatically discoverable and usable by AI assistants.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

try:
    from scripts.langsmith_debug_tool import LangSmithDebugTool
except ImportError:
    print("❌ LangSmith debug tool not available")

class LangSmithDebugger:
    """Automatic LangSmith debugger for AI assistants."""
    
    def __init__(self):
        # Get API key from environment variable
        import os
        self.api_key = os.getenv('LANGSMITH_API_KEY')
        self.project_name = os.getenv('LANGSMITH_PROJECT', 'telegram-reminder-bot')
        
        if not self.api_key:
            raise ValueError("LANGSMITH_API_KEY not found in environment variables")
        
        self.tool = LangSmithDebugTool(self.api_key, self.project_name)
    
    def get_recent_traces(self, limit: int = 5) -> Dict[str, Any]:
        """Get recent traces for quick analysis."""
        traces = self.tool.get_recent_traces(limit)
        return {
            "action": "recent_traces",
            "traces": traces,
            "summary": f"Found {len(traces)} recent traces"
        }
    
    def analyze_trace(self, trace_id: str) -> Dict[str, Any]:
        """Analyze a specific trace for debugging."""
        analysis = self.tool.analyze_trace(trace_id)
        return {
            "action": "trace_analysis",
            "trace_id": trace_id,
            "analysis": analysis
        }
    
    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics for monitoring."""
        metrics = self.tool.get_performance_metrics(hours)
        return {
            "action": "performance_metrics",
            "metrics": metrics
        }
    
    def search_user_traces(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Search traces for a specific user."""
        traces = self.tool.search_traces_by_user(user_id, limit)
        return {
            "action": "user_traces",
            "user_id": user_id,
            "traces": traces
        }
    
    def debug_issue(self, description: str) -> Dict[str, Any]:
        """Debug an issue based on description."""
        # Get recent traces to analyze
        traces = self.tool.get_recent_traces(10)
        
        # Look for traces that might match the issue
        relevant_traces = []
        for trace in traces:
            if trace.get('error') or trace.get('status') == 'failed':
                relevant_traces.append(trace)
        
        return {
            "action": "issue_debug",
            "description": description,
            "relevant_traces": relevant_traces,
            "recommendation": "Check the relevant traces above for potential issues"
        }

# Global instance for easy access
langsmith_debugger = LangSmithDebugger()

def debug_bot(issue_description: str = None, action: str = "recent", **kwargs) -> Dict[str, Any]:
    """
    Main debugging function that can be called automatically.
    
    Args:
        issue_description: Description of the issue to debug
        action: Action to perform (recent, analyze, metrics, search, debug)
        **kwargs: Additional arguments
    
    Returns:
        Debugging information
    """
    if issue_description:
        return langsmith_debugger.debug_issue(issue_description)
    
    if action == "recent":
        return langsmith_debugger.get_recent_traces(kwargs.get('limit', 5))
    elif action == "analyze" and kwargs.get('trace_id'):
        return langsmith_debugger.analyze_trace(kwargs['trace_id'])
    elif action == "metrics":
        return langsmith_debugger.get_performance_metrics(kwargs.get('hours', 24))
    elif action == "search" and kwargs.get('user_id'):
        return langsmith_debugger.search_user_traces(kwargs['user_id'], kwargs.get('limit', 10))
    else:
        return {"error": "Invalid action or missing parameters"}

# Auto-discovery function
def get_available_tools() -> List[str]:
    """Return list of available debugging tools."""
    return [
        "debug_bot",
        "get_recent_traces", 
        "analyze_trace",
        "get_performance_metrics",
        "search_user_traces",
        "debug_issue"
    ]

if __name__ == "__main__":
    # Command line interface
    if len(sys.argv) > 1:
        action = sys.argv[1]
        kwargs = {}
        
        if action == "analyze" and len(sys.argv) > 2:
            kwargs['trace_id'] = sys.argv[2]
        elif action == "search" and len(sys.argv) > 2:
            kwargs['user_id'] = sys.argv[2]
        elif action == "recent" and len(sys.argv) > 2:
            kwargs['limit'] = int(sys.argv[2])
        
        result = debug_bot(action=action, **kwargs)
        print(json.dumps(result, indent=2))
    else:
        # Default: get recent traces
        result = debug_bot()
        print(json.dumps(result, indent=2)) 