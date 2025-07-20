#!/usr/bin/env python3
"""
LangSmith Debug Tool

This tool provides direct access to LangSmith traces for debugging the Telegram bot.
It can be used to analyze traces, identify issues, and provide debugging insights.
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from langsmith import Client
    from langsmith.run_trees import RunTree
except ImportError:
    print("❌ LangSmith not available. Please install: pip install langsmith")
    sys.exit(1)

class LangSmithDebugTool:
    """Tool for debugging Telegram bot using LangSmith traces."""
    
    def __init__(self, api_key: str, project_name: str = "telegram-reminder-bot"):
        self.client = Client(api_key=api_key)
        self.project_name = project_name
    
    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent traces from the project."""
        try:
            traces = list(self.client.list_runs(
                project_name=self.project_name,
                limit=limit
            ))
            
            return [{
                'id': str(trace.id),
                'name': trace.name,
                'status': trace.status,
                'start_time': trace.start_time.isoformat() if trace.start_time else None,
                'end_time': trace.end_time.isoformat() if trace.end_time else None,
                'error': trace.error if hasattr(trace, 'error') else None
            } for trace in traces]
        except Exception as e:
            return [{'error': f'Failed to fetch traces: {str(e)}'}]
    
    def get_trace_details(self, trace_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific trace."""
        try:
            trace = self.client.read_run(trace_id)
            
            # Get child runs (nodes)
            child_runs = list(self.client.list_runs(
                project_name=self.project_name,
                filter=f"parent_run_id = '{trace_id}'"
            ))
            
            trace_data = {
                'id': str(trace.id),
                'name': trace.name,
                'status': trace.status,
                'start_time': trace.start_time.isoformat() if trace.start_time else None,
                'end_time': trace.end_time.isoformat() if trace.end_time else None,
                'error': trace.error if hasattr(trace, 'error') else None,
                'inputs': trace.inputs,
                'outputs': trace.outputs,
                'child_runs': []
            }
            
            # Add child run details
            for child in child_runs:
                child_data = {
                    'id': str(child.id),
                    'name': child.name,
                    'status': child.status,
                    'start_time': child.start_time.isoformat() if child.start_time else None,
                    'end_time': child.end_time.isoformat() if child.end_time else None,
                    'duration': (child.end_time - child.start_time).total_seconds() if child.end_time and child.start_time else None,
                    'inputs': child.inputs,
                    'outputs': child.outputs,
                    'error': child.error if hasattr(child, 'error') else None
                }
                trace_data['child_runs'].append(child_data)
            
            return trace_data
        except Exception as e:
            return {'error': f'Failed to fetch trace details: {str(e)}'}
    
    def analyze_trace(self, trace_id: str) -> Dict[str, Any]:
        """Analyze a trace and identify potential issues."""
        trace_data = self.get_trace_details(trace_id)
        
        if 'error' in trace_data:
            return trace_data
        
        analysis = {
            'trace_id': trace_id,
            'overall_status': trace_data['status'],
            'total_duration': None,
            'issues': [],
            'performance_issues': [],
            'node_analysis': {},
            'recommendations': []
        }
        
        # Calculate total duration
        if trace_data['start_time'] and trace_data['end_time']:
            start = datetime.fromisoformat(trace_data['start_time'])
            end = datetime.fromisoformat(trace_data['end_time'])
            analysis['total_duration'] = (end - start).total_seconds()
        
        # Analyze each node
        for child in trace_data['child_runs']:
            node_name = child['name']
            analysis['node_analysis'][node_name] = {
                'status': child['status'],
                'duration': child['duration'],
                'has_error': bool(child.get('error')),
                'error': child.get('error')
            }
            
            # Check for issues
            if child['status'] == 'failed':
                analysis['issues'].append(f"Node '{node_name}' failed: {child.get('error', 'Unknown error')}")
            
            # Check for performance issues
            if child['duration'] and child['duration'] > 5.0:
                analysis['performance_issues'].append(f"Node '{node_name}' took {child['duration']:.2f}s (slow)")
            
            # Specific node analysis
            if node_name == 'determine_intent_node':
                if 'outputs' in child and child['outputs']:
                    intent = child['outputs'].get('current_intent', 'unknown')
                    analysis['node_analysis'][node_name]['detected_intent'] = intent
            
            elif node_name == 'process_datetime_node':
                if 'outputs' in child and child['outputs']:
                    parsed_datetime = child['outputs'].get('parsed_datetime')
                    analysis['node_analysis'][node_name]['parsed_datetime'] = parsed_datetime
        
        # Generate recommendations
        if analysis['issues']:
            analysis['recommendations'].append("Fix the failed nodes first")
        
        if analysis['performance_issues']:
            analysis['recommendations'].append("Optimize slow nodes for better performance")
        
        if analysis['total_duration'] and analysis['total_duration'] > 10.0:
            analysis['recommendations'].append("Overall trace is slow - consider optimization")
        
        return analysis
    
    def search_traces_by_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search traces by user ID."""
        try:
            traces = list(self.client.list_runs(
                project_name=self.project_name,
                filter=f"inputs.user_id = '{user_id}'",
                limit=limit
            ))
            
            return [{
                'id': str(trace.id),
                'name': trace.name,
                'status': trace.status,
                'start_time': trace.start_time.isoformat() if trace.start_time else None,
                'inputs': trace.inputs
            } for trace in traces]
        except Exception as e:
            return [{'error': f'Failed to search traces: {str(e)}'}]
    
    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics for the last N hours."""
        try:
            since = datetime.now() - timedelta(hours=hours)
            traces = list(self.client.list_runs(
                project_name=self.project_name,
                start_time=since
            ))
            
            total_traces = len(traces)
            successful_traces = len([t for t in traces if t.status == 'success'])
            failed_traces = len([t for t in traces if t.status == 'failed'])
            
            # Calculate average duration
            durations = []
            for trace in traces:
                if trace.start_time and trace.end_time:
                    duration = (trace.end_time - trace.start_time).total_seconds()
                    durations.append(duration)
            
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            return {
                'total_traces': total_traces,
                'successful_traces': successful_traces,
                'failed_traces': failed_traces,
                'success_rate': (successful_traces / total_traces * 100) if total_traces > 0 else 0,
                'average_duration': avg_duration,
                'time_period': f'Last {hours} hours'
            }
        except Exception as e:
            return {'error': f'Failed to get metrics: {str(e)}'}

def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='LangSmith Debug Tool')
    parser.add_argument('--api-key', required=True, help='LangSmith API key')
    parser.add_argument('--project', default='telegram-reminder-bot', help='Project name')
    parser.add_argument('--action', required=True, choices=['recent', 'trace', 'analyze', 'search', 'metrics'], help='Action to perform')
    parser.add_argument('--trace-id', help='Trace ID for trace/analyze actions')
    parser.add_argument('--user-id', help='User ID for search action')
    parser.add_argument('--limit', type=int, default=10, help='Limit for recent/search actions')
    parser.add_argument('--hours', type=int, default=24, help='Hours for metrics action')
    
    args = parser.parse_args()
    
    tool = LangSmithDebugTool(args.api_key, args.project)
    
    if args.action == 'recent':
        traces = tool.get_recent_traces(args.limit)
        print(json.dumps(traces, indent=2))
    
    elif args.action == 'trace':
        if not args.trace_id:
            print("❌ Trace ID required for trace action")
            sys.exit(1)
        trace_data = tool.get_trace_details(args.trace_id)
        print(json.dumps(trace_data, indent=2))
    
    elif args.action == 'analyze':
        if not args.trace_id:
            print("❌ Trace ID required for analyze action")
            sys.exit(1)
        analysis = tool.analyze_trace(args.trace_id)
        print(json.dumps(analysis, indent=2))
    
    elif args.action == 'search':
        if not args.user_id:
            print("❌ User ID required for search action")
            sys.exit(1)
        traces = tool.search_traces_by_user(args.user_id, args.limit)
        print(json.dumps(traces, indent=2))
    
    elif args.action == 'metrics':
        metrics = tool.get_performance_metrics(args.hours)
        print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main() 