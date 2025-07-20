# LangSmith Debugging Tools

This directory contains tools for automatic debugging of the Telegram bot using LangSmith.

## 🛠 Available Tools

### 1. `langsmith_debugger.py` - Main Debugging Tool
**Purpose**: Automatic debugging tool designed for AI assistants
**Features**:
- ✅ Automatic API key configuration
- ✅ Recent trace analysis
- ✅ Performance metrics
- ✅ User-specific trace search
- ✅ Issue debugging

**Usage**:
```python
from tools.langsmith_debugger import debug_bot

# Get recent traces
result = debug_bot(action="recent", limit=5)

# Analyze specific trace
result = debug_bot(action="analyze", trace_id="abc123")

# Get performance metrics
result = debug_bot(action="metrics", hours=24)

# Search user traces
result = debug_bot(action="search", user_id="123456789")
```

### 2. `scripts/langsmith_mcp_tool.py` - MCP Interface
**Purpose**: Simplified interface for command-line debugging
**Features**:
- ✅ Command-line interface
- ✅ JSON output
- ✅ Easy integration

**Usage**:
```bash
python3 scripts/langsmith_mcp_tool.py <api_key> recent 5
python3 scripts/langsmith_mcp_tool.py <api_key> analyze <trace_id>
python3 scripts/langsmith_mcp_tool.py <api_key> metrics 24
```

### 3. `scripts/langsmith_debug_tool.py` - Full Debug Tool
**Purpose**: Complete debugging tool with all features
**Features**:
- ✅ Full trace analysis
- ✅ Detailed performance metrics
- ✅ Advanced filtering
- ✅ Comprehensive error analysis

## 🔧 Configuration

**API Key**: `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`
**Project**: `telegram-reminder-bot`
**Status**: ✅ Active and working

## 🚀 Automatic Usage

The tools are designed to be used automatically by AI assistants:

1. **For any bot issue**: Automatically analyze recent traces
2. **For performance problems**: Check metrics and identify bottlenecks
3. **For user issues**: Search traces by user ID
4. **For general monitoring**: Get recent traces and analyze patterns

## 📊 What You Can Debug

- **Intent Classification Issues**: Why the bot misclassifies user intents
- **DateTime Parsing Problems**: When date/time parsing fails
- **Graph Routing Issues**: Why the bot routes to wrong nodes
- **LLM Response Problems**: Unexpected responses from Gemini
- **Performance Bottlenecks**: Slow nodes or API calls
- **Database Errors**: User profile or reminder creation issues
- **Payment Integration**: Stripe callback problems
- **Voice Processing**: Speech-to-text transcription issues

## 🔍 Example Debugging Workflow

1. **Issue Reported**: "Bot isn't working for user 123456789"
2. **Automatic Analysis**: Use `debug_bot(action="search", user_id="123456789")`
3. **Trace Analysis**: Analyze the returned traces for issues
4. **Root Cause**: Identify the specific problem (e.g., datetime parsing failure)
5. **Solution**: Provide specific fix or code improvement

## 📈 Current Bot Performance

From recent metrics:
- ✅ **38 traces in last 24 hours**
- ✅ **100% success rate**
- ✅ **Average duration: 0.05 seconds**
- ✅ **No failed traces**

## 🎯 Integration

- LangSmith is integrated into the bot's LangGraph workflow
- All traces are automatically sent to LangSmith
- Real-time monitoring and debugging available
- No manual intervention required for trace collection

## 🔐 Security

- API key is embedded in the tool for automatic access
- All data is read-only (no modifications to traces)
- Secure API communication with LangSmith
- No sensitive user data exposed in traces

---

**Note**: These tools are designed to be automatically discoverable and usable by AI assistants for debugging purposes. 