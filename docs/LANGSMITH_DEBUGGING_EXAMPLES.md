# LangSmith Debugging Examples

This guide provides practical examples of how to use LangSmith to debug common issues in the Telegram Reminder Bot.

## Example 1: Debugging Intent Misclassification

### Problem
A user sends "remind me to call mom tomorrow at 10 AM" but the bot detects the wrong intent.

### Debugging Steps

1. **Find the Trace**
   - Go to LangSmith dashboard
   - Search for the user ID or timestamp
   - Look for traces with the input text

2. **Examine the Flow**
   ```
   entry_node → load_user_profile_node → determine_intent_node → [wrong routing]
   ```

3. **Check determine_intent_node Details**
   - Click on `determine_intent_node`
   - Examine the LLM prompt sent to Gemini
   - Check the LLM response
   - Look for any parsing errors

4. **Common Issues to Look For**
   - LLM returning unexpected intent
   - Prompt not clear enough
   - Input preprocessing issues

### Example Trace Analysis
```
Input: "remind me to call mom tomorrow at 10 AM"
Expected Intent: intent_create_reminder
Actual Intent: intent_unknown

LLM Prompt: "Classify the intent of this message..."
LLM Response: "This appears to be a general conversation message"
```

**Solution**: The prompt might need to be more specific about reminder creation patterns.

## Example 2: Debugging DateTime Parsing Issues

### Problem
The bot fails to parse "next Monday at 3 PM" correctly.

### Debugging Steps

1. **Find the Trace**
   - Search for the specific datetime input
   - Look for traces in `process_datetime_node`

2. **Examine the DateTime Processing**
   ```
   process_datetime_node → validate_and_clarify_reminder_node
   ```

3. **Check LLM Interactions**
   - Look at the datetime parsing prompt
   - Examine the LLM response
   - Check if the parsed datetime is correct

4. **Common Issues**
   - LLM not understanding relative dates
   - Timezone confusion
   - Ambiguous date/time combinations

### Example Trace Analysis
```
Input: "next Monday at 3 PM"
LLM Response: "I cannot determine the exact date for 'next Monday'"
Parsed DateTime: None
Error: Date parsing failed
```

**Solution**: The prompt needs better examples of relative date parsing.

## Example 3: Debugging Database Errors

### Problem
User profile loading fails with a database error.

### Debugging Steps

1. **Find the Trace**
   - Search for the user ID
   - Look for traces that fail at `load_user_profile_node`

2. **Examine the Error**
   ```
   entry_node → load_user_profile_node → [ERROR]
   ```

3. **Check Error Details**
   - Look at the error message in the trace
   - Check if it's a connection issue
   - Verify if it's a data integrity problem

4. **Common Issues**
   - Database connection timeout
   - Missing user record
   - Corrupted data

### Example Trace Analysis
```
Node: load_user_profile_node
Error: "Database connection failed: timeout"
User ID: 123456789
```

**Solution**: Check database connectivity and connection pool settings.

## Example 4: Debugging Payment Integration Issues

### Problem
Payment callback processing fails.

### Debugging Steps

1. **Find the Trace**
   - Search for payment-related traces
   - Look for traces with payment callback data

2. **Examine the Payment Flow**
   ```
   payment_callback → validate_payment → update_subscription → [ERROR]
   ```

3. **Check Payment Data**
   - Verify Stripe webhook signature
   - Check payment status
   - Examine user subscription update

4. **Common Issues**
   - Invalid webhook signature
   - Payment already processed
   - Database update failure

### Example Trace Analysis
```
Payment ID: pi_123456789
Status: succeeded
Webhook Signature: valid
Error: "User subscription update failed: user not found"
```

**Solution**: Check if the user exists in the database before updating subscription.

## Example 5: Debugging Voice Message Processing

### Problem
Voice message transcription fails or returns incorrect text.

### Debugging Steps

1. **Find the Trace**
   - Search for voice message traces
   - Look for traces in `voice_utils.py`

2. **Examine Voice Processing**
   ```
   voice_message → transcribe_audio → process_text → [ERROR]
   ```

3. **Check Transcription**
   - Verify audio file format
   - Check Google Speech-to-Text response
   - Examine transcription accuracy

4. **Common Issues**
   - Audio file too large
   - Unsupported audio format
   - Poor audio quality
   - Language detection issues

### Example Trace Analysis
```
Audio File: voice_message.ogg
File Size: 2.5MB
Transcription: "remind me to call mom tomorrow at 10 AM"
Expected: "remind me to call mom tomorrow at 10 AM"
Status: Success
```

**Solution**: The transcription is working correctly.

## Example 6: Debugging Graph Routing Issues

### Problem
The bot gets stuck in a conversation loop or routes to the wrong node.

### Debugging Steps

1. **Find the Trace**
   - Search for the user's conversation
   - Look for repeated patterns

2. **Examine the Graph Flow**
   ```
   determine_intent_node → [wrong routing] → handle_intent_node → determine_intent_node
   ```

3. **Check Routing Logic**
   - Examine conditional edge functions
   - Check state data at each node
   - Verify intent classification

4. **Common Issues**
   - Intent not properly cleared
   - State not updated correctly
   - Routing conditions too broad

### Example Trace Analysis
```
Node: determine_intent_node
Intent: intent_create_reminder
Routing: handle_intent_node (should be process_datetime_node)
State: {"current_intent": "intent_create_reminder", "extracted_parameters": {...}}
```

**Solution**: Check the routing logic in `route_after_intent_determination`.

## Example 7: Debugging Performance Issues

### Problem
The bot responds slowly to user messages.

### Debugging Steps

1. **Find Slow Traces**
   - Filter traces by duration
   - Look for traces taking >5 seconds

2. **Examine Node Timing**
   - Check which nodes are slow
   - Look for LLM call delays
   - Examine database query times

3. **Identify Bottlenecks**
   - LLM API calls
   - Database queries
   - External API calls

4. **Common Issues**
   - Slow LLM responses
   - Database connection pool exhaustion
   - Network latency

### Example Trace Analysis
```
Total Duration: 8.2 seconds
- entry_node: 0.1s
- load_user_profile_node: 2.1s (slow database query)
- determine_intent_node: 5.8s (slow LLM call)
- format_response_node: 0.2s
```

**Solution**: Optimize database queries and consider LLM caching.

## Example 8: Debugging Memory Issues

### Problem
The bot runs out of memory or becomes unresponsive.

### Debugging Steps

1. **Find Memory-Intensive Traces**
   - Look for traces with large state data
   - Check for memory leaks in conversation memory

2. **Examine State Management**
   - Check if conversation memory is cleared
   - Look for accumulated state data
   - Verify checkpoint cleanup

3. **Common Issues**
   - Conversation memory not cleared
   - Large file attachments
   - Accumulated state data

### Example Trace Analysis
```
State Size: 2.3MB (very large)
Conversation Memory: 50+ messages
File Attachments: 3 voice messages
```

**Solution**: Implement conversation memory cleanup and file size limits.

## Best Practices for LangSmith Debugging

### 1. Use Descriptive Run Names
```python
from src.langsmith_config import create_run_name

run_name = create_run_name(user_id, "create_reminder")
```

### 2. Add Custom Metadata
```python
log_graph_execution(user_id, "custom_node", {
    "custom_data": "value",
    "debug_info": "additional context"
})
```

### 3. Filter Traces Effectively
- Use user ID for specific user issues
- Filter by date/time for recent problems
- Search by error messages for failures
- Filter by node name for specific functionality

### 4. Set Up Alerts
- Monitor error rates
- Track response times
- Alert on critical failures
- Monitor memory usage

### 5. Regular Trace Review
- Review traces daily during development
- Check for patterns in failures
- Monitor performance trends
- Validate new features

## Conclusion

LangSmith provides powerful debugging capabilities for your Telegram bot. By following these examples and best practices, you can quickly identify and resolve issues, improve performance, and ensure a better user experience.

Remember to:
- Use descriptive trace names
- Add relevant metadata
- Monitor performance regularly
- Set up appropriate alerts
- Review traces systematically 