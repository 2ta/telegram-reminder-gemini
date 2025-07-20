# LangSmith Automatic Debugging Guide

This document provides comprehensive information about the automatic LangSmith debugging capabilities integrated into this project.

## 🎯 **Purpose**

This system allows AI assistants to automatically debug the Telegram bot using LangSmith traces without requiring manual reminders or setup.

## 🛠 **Available Tools**

### 1. **Main Debugging Tool** (`tools/langsmith_debugger.py`)
- **Purpose**: Automatic debugging tool designed for AI assistants
- **API Key**: Read from environment variable (LANGSMITH_API_KEY)
- **Project**: `telegram-reminder-bot`
- **Status**: ✅ Active and working

### 2. **MCP Interface** (`scripts/langsmith_mcp_tool.py`)
- **Purpose**: Simplified command-line interface
- **Features**: JSON output, easy integration

### 3. **Full Debug Tool** (`scripts/langsmith_debug_tool.py`)
- **Purpose**: Complete debugging tool with all features
- **Features**: Advanced analysis, detailed metrics

## 🚀 **Automatic Usage Instructions**

### **For AI Assistants (Automatic Discovery)**

When debugging any bot issue, automatically use:

```python
from tools.langsmith_debugger import debug_bot

# Get recent traces (default)
result = debug_bot()

# Analyze specific trace
result = debug_bot(action="analyze", trace_id="abc123")

# Get performance metrics
result = debug_bot(action="metrics", hours=24)

# Search user traces
result = debug_bot(action="search", user_id="123456789")
```

### **Command Line Usage**

```bash
# Get recent traces
python3 tools/langsmith_debugger.py

# Get recent traces with limit
python3 tools/langsmith_debugger.py recent 10

# Analyze specific trace
python3 tools/langsmith_debugger.py analyze <trace_id>

# Get metrics
python3 tools/langsmith_debugger.py metrics 24
```

## 📊 **What Can Be Debugged**

### **1. Intent Classification Issues**
- **Problem**: Bot misclassifies user intents
- **Debug**: Check `determine_intent_node` traces
- **Solution**: Analyze LLM prompts and responses

### **2. DateTime Parsing Problems**
- **Problem**: Bot fails to parse date/time
- **Debug**: Check `process_datetime_node` traces
- **Solution**: Review datetime parsing logic

### **3. Graph Routing Issues**
- **Problem**: Bot routes to wrong nodes
- **Debug**: Check routing logic in traces
- **Solution**: Analyze conditional edge functions

### **4. LLM Response Problems**
- **Problem**: Unexpected responses from Gemini
- **Debug**: Check LLM call traces
- **Solution**: Review prompts and model configuration

### **5. Performance Bottlenecks**
- **Problem**: Slow response times
- **Debug**: Check node durations in traces
- **Solution**: Optimize slow nodes

### **6. Database Errors**
- **Problem**: User profile or reminder creation fails
- **Debug**: Check database operation traces
- **Solution**: Review database queries and connections

### **7. Payment Integration Issues**
- **Problem**: Stripe callback processing fails
- **Debug**: Check payment-related traces
- **Solution**: Review webhook handling

### **8. Voice Processing Issues**
- **Problem**: Speech-to-text transcription fails
- **Debug**: Check voice processing traces
- **Solution**: Review audio file handling

## 🔍 **Debugging Workflow**

### **Step 1: Issue Identification**
- User reports problem
- Identify the type of issue (intent, datetime, performance, etc.)

### **Step 2: Automatic Trace Analysis**
```python
# For general issues
result = debug_bot(action="recent", limit=10)

# For user-specific issues
result = debug_bot(action="search", user_id="123456789")

# For performance issues
result = debug_bot(action="metrics", hours=24)
```

### **Step 3: Trace Analysis**
- Review the returned traces
- Identify failed nodes or slow operations
- Check error messages and durations

### **Step 4: Root Cause Analysis**
- Analyze specific node outputs
- Check LLM responses
- Review state transitions

### **Step 5: Solution Implementation**
- Provide specific code fixes
- Suggest prompt improvements
- Recommend optimizations

## 📈 **Current Bot Performance**

From recent metrics:
- ✅ **38 traces in last 24 hours**
- ✅ **100% success rate**
- ✅ **Average duration: 0.05 seconds**
- ✅ **No failed traces**

## 🎯 **Integration Details**

### **LangSmith Configuration**
- **API Key**: Set in environment variables (LANGSMITH_API_KEY)
- **Project**: `telegram-reminder-bot`
- **Tracing**: Enabled for all LangGraph nodes
- **Status**: ✅ Active on server

### **Automatic Trace Collection**
- All bot interactions are automatically traced
- No manual intervention required
- Real-time monitoring available
- Traces include all node inputs/outputs

## 🔐 **Security & Privacy**

- **Read-only access**: Tools only read trace data
- **No modifications**: Cannot modify traces or bot behavior
- **Secure API**: Uses official LangSmith API
- **Data protection**: No sensitive user data exposed

## 📝 **Example Debugging Sessions**

### **Example 1: Intent Classification Issue**
```
User: "Bot isn't understanding 'remind me to call mom tomorrow'"

Debug Steps:
1. debug_bot(action="recent", limit=5)
2. Look for traces with similar input
3. Check determine_intent_node outputs
4. Analyze LLM responses
5. Provide prompt improvement suggestions
```

### **Example 2: Performance Issue**
```
User: "Bot is responding slowly"

Debug Steps:
1. debug_bot(action="metrics", hours=24)
2. Check average duration
3. Identify slow nodes
4. Analyze node durations in recent traces
5. Suggest optimizations
```

### **Example 3: User-Specific Issue**
```
User: "Bot isn't working for user 123456789"

Debug Steps:
1. debug_bot(action="search", user_id="123456789")
2. Analyze user's recent traces
3. Check for failed nodes
4. Identify specific issues
5. Provide targeted fixes
```

## 🚀 **Best Practices**

### **For AI Assistants**
1. **Always check recent traces** when debugging issues
2. **Use specific trace analysis** for detailed problems
3. **Check performance metrics** for optimization opportunities
4. **Search by user ID** for user-specific issues
5. **Provide actionable solutions** based on trace analysis

### **For Developers**
1. **Monitor traces regularly** for patterns
2. **Set up alerts** for failed traces
3. **Review performance metrics** weekly
4. **Use trace analysis** for optimization
5. **Document common issues** and solutions

## 📚 **Related Documentation**

- [LangSmith Integration Guide](LANGSMITH_INTEGRATION.md)
- [LangSmith Debugging Examples](LANGSMITH_DEBUGGING_EXAMPLES.md)
- [Project Rules](../.rules) - Contains LangSmith configuration
- [Tools README](../tools/README.md) - Tool documentation

---

**Note**: This system is designed to be automatically discoverable and usable by AI assistants. No manual setup or reminders are required for debugging capabilities. 