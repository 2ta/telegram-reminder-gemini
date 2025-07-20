# LangSmith Integration Guide

This document explains how to set up and use LangSmith for monitoring, debugging, and tracing your Telegram Reminder Bot's LangGraph application.

## What is LangSmith?

LangSmith is a platform for debugging, testing, evaluating, and monitoring LLM applications and chains. It provides:

- **Tracing**: Visualize the execution flow of your LangGraph application
- **Debugging**: Inspect inputs, outputs, and intermediate steps
- **Testing**: Create and run test suites for your application
- **Monitoring**: Track performance and identify issues in production
- **Evaluation**: Compare different models and prompts

## Setup Instructions

### 1. Get a LangSmith API Key

1. Visit [https://smith.langchain.com/](https://smith.langchain.com/)
2. Sign up for a free account
3. Navigate to your API Keys section
4. Create a new API key
5. Copy the API key for use in your environment

### 2. Configure Environment Variables

Add the following variables to your `.env` file:

```bash
# LangSmith Configuration
LANGSMITH_API_KEY=your_api_key_here
LANGSMITH_PROJECT=telegram-reminder-bot
LANGSMITH_TRACING_V2=True
```

**Configuration Options:**
- `LANGSMITH_API_KEY` (required): Your LangSmith API key
- `LANGSMITH_PROJECT` (optional): Project name for organizing traces (defaults to "telegram-reminder-bot")
- `LANGSMITH_ENDPOINT` (optional): Custom LangSmith endpoint (uses default if not set)
- `LANGSMITH_TRACING_V2` (optional): Enable LangSmith tracing v2 (default: True)

### 3. Install Dependencies

The required dependencies are already included in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## How It Works

### Automatic Tracing

Once configured, LangSmith will automatically trace:

1. **Graph Execution**: Each node in your LangGraph workflow
2. **LLM Calls**: All interactions with the Gemini model
3. **State Transitions**: How data flows between nodes
4. **Error Handling**: Any exceptions or failures

### Manual Logging

The integration includes manual logging capabilities for custom events:

```python
from src.langsmith_config import log_graph_execution

# Log custom events
log_graph_execution(user_id, "custom_node", {"custom_data": "value"})
```

## Viewing Traces

### 1. Access LangSmith Dashboard

1. Go to [https://smith.langchain.com/](https://smith.langchain.com/)
2. Navigate to your project
3. View the "Traces" section

### 2. Understanding Trace Data

Each trace shows:
- **Input**: The user's message and context
- **Graph Flow**: Visual representation of node execution
- **Node Details**: Inputs, outputs, and processing time for each node
- **LLM Interactions**: Prompts sent to Gemini and responses received
- **Final Output**: The bot's response to the user

### 3. Filtering and Searching

You can filter traces by:
- Date and time
- User ID
- Intent type
- Node name
- Success/failure status

## Debugging with LangSmith

### 1. Identifying Issues

Use LangSmith to:
- **Track User Journeys**: Follow a user's complete interaction flow
- **Identify Bottlenecks**: See which nodes take the most time
- **Debug Failures**: Examine the exact point where things go wrong
- **Validate Logic**: Ensure your routing logic works as expected

### 2. Example Debugging Workflow

1. **Find the Trace**: Search for a specific user ID or timestamp
2. **Examine the Flow**: Look at the visual graph representation
3. **Check Node Details**: Click on any node to see inputs/outputs
4. **Review LLM Calls**: Examine the prompts and responses
5. **Identify Issues**: Look for unexpected outputs or errors

### 3. Common Issues to Look For

- **Intent Misclassification**: Wrong intent detected
- **DateTime Parsing Errors**: Failed to parse user's time/date input
- **Database Errors**: Issues with user profile or reminder creation
- **LLM Response Issues**: Unexpected or malformed responses from Gemini

## Testing with LangSmith

### 1. Creating Test Datasets

You can create test datasets in LangSmith to:
- Test different user inputs
- Validate intent detection
- Ensure proper reminder creation
- Test error handling

### 2. Running Evaluations

Use LangSmith's evaluation features to:
- Compare different model versions
- Test prompt variations
- Measure accuracy and performance
- Identify areas for improvement

## Production Monitoring

### 1. Performance Metrics

Monitor:
- **Response Times**: How long each node takes to execute
- **Success Rates**: Percentage of successful interactions
- **Error Patterns**: Common failure points
- **User Satisfaction**: Track user feedback and behavior

### 2. Alerting

Set up alerts for:
- High error rates
- Slow response times
- Unusual traffic patterns
- System failures

## Best Practices

### 1. Privacy and Security

- **User Data**: Be mindful of sensitive user information in traces
- **API Keys**: Keep your LangSmith API key secure
- **Data Retention**: Consider trace retention policies

### 2. Performance

- **Sampling**: Consider sampling traces in high-traffic scenarios
- **Cleanup**: Regularly clean up old traces to manage storage
- **Monitoring**: Set up dashboards for key metrics

### 3. Development Workflow

- **Local Development**: Use LangSmith during development for debugging
- **Testing**: Create test suites for critical user journeys
- **Deployment**: Monitor production traces for issues

## Troubleshooting

### Common Issues

1. **No Traces Appearing**
   - Check your API key is correct
   - Verify environment variables are set
   - Ensure the bot is running and processing messages

2. **Missing Data in Traces**
   - Check that LangSmith is properly initialized
   - Verify logging calls are working
   - Look for any error messages in logs

3. **Performance Issues**
   - Consider reducing trace sampling
   - Check network connectivity to LangSmith
   - Monitor API rate limits

### Getting Help

- **LangSmith Documentation**: [https://docs.smith.langchain.com/](https://docs.smith.langchain.com/)
- **LangSmith Support**: Available through the LangSmith platform
- **Project Issues**: Use the project's issue tracker for bot-specific problems

## Example Trace Analysis

Here's what a typical trace might look like for a user creating a reminder:

```
User Input: "Remind me to call mom tomorrow at 10 AM"

Trace Flow:
1. entry_node → Processes initial input
2. load_user_profile_node → Loads user data from database
3. determine_intent_node → Detects "create_reminder" intent
4. process_datetime_node → Parses "tomorrow at 10 AM"
5. validate_and_clarify_reminder_node → Validates reminder details
6. confirm_reminder_details_node → Asks for confirmation
7. format_response_node → Formats final response

LLM Interactions:
- Intent detection prompt
- DateTime parsing prompt
- Validation prompt
- Response formatting prompt
```

This trace would show the complete flow, timing, and any issues that occurred during processing. 