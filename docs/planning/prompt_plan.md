
## Phase 1: Foundation Setup

### Step 1: Project Initialization

```
# Project Initialization for Telegram Reminder Bot

We're starting development of a Persian language Reminder bot for Telegram. Create the initial project setup including:

1. Project directory structure:
   - src/ (main source code)
   - tests/ (test files)
   - resources/ (language resources, prompts)
   - logs/ (log output files)
   - config/ (configuration files)

2. requirements.txt with all dependencies:
   - python-telegram-bot
   - langgraph
   - google-cloud-speech
   - google-generativeai
   - sqlalchemy
   - alembic
   - jdatetime (for Jalali calendar support)
   - pytest (and related testing libraries)

3. Configuration management:
   - Create config.py with environment variable loading
   - Support for different environments (dev, test, prod)
   - Telegram API token configuration
   - Database configuration

4. Logging setup:
   - Implement rotating file logger
   - Console logging for development
   - Proper log levels and formatting

5. Create a basic README.md with project description and setup instructions

6. Add a simple test to verify the setup works correctly

Use Python 3.9+ and follow best practices including type hints, docstrings, and modular design.
```


### Step 2: Database Design

```
# Database Models Implementation for Reminder Bot

Now let's implement the database models for our Telegram bot using SQLAlchemy. We need to track users, their subscription status, and their reminders.

1. Create a base SQLAlchemy model with common fields:
   - id (primary key)
   - created_at
   - updated_at

2. Implement User model:
   - telegram_id (unique)
   - first_name, last_name, username
   - language_code (default 'fa')
   - subscription_tier (FREE, STANDARD, PREMIUM)
   - subscription_expiry (nullable datetime)
   - reminder_count (for quick limit checking)

3. Implement Reminder model:
   - user_id (foreign key to User)
   - task (text description)
   - jalali_date (stored in a queryable format)
   - time (time of day)
   - is_active (boolean)
   - is_notified (boolean)
   - notification_sent_at (nullable datetime)

4. Create a database connection utility:
   - Engine creation function
   - Session management
   - Table creation function

5. Write unit tests for:
   - Model instantiation
   - Default values
   - Relationships between models
   - Database operations (CRUD)

Ensure proper handling of Jalali dates (storing in a format that supports date comparisons while preserving the original calendar system).
```


### Step 3: Basic Telegram Bot Setup

```
# Basic Telegram Bot Implementation

Let's implement the core Telegram bot functionality that will receive and respond to messages. We'll add the reminder-specific logic later.

1. Create a bot module with:
   - Bot initialization function using the token from config
   - Basic error handling
   - Connection to Telegram API

2. Implement command handlers for:
   - /start - welcome message and bot introduction
   - /help - List of commands and capabilities
   - /privacy - Privacy information

3. Create a basic message handler that:
   - Receives text messages
   - Logs incoming messages
   - Responds with a simple acknowledgment

4. Implement user management:
   - Create or update user records when users interact with bot
   - Set default subscription tier to FREE

5. Create a bot runner module:
   - Main entry point for the application
   - Proper shutdown handling

6. Write tests for:
   - Command handlers (mocking the Telegram API)
   - Message reception and response
   - User creation/update logic

Focus on making the code modular and testable. All user-facing messages should be in Persian and we should prepare for internationalization from the start.
```


## Phase 2: Core Functionality

### Step 4: Voice Message Processing

```
# Voice Message Processing Implementation

Now let's implement the voice message handling functionality that will convert voice messages to text using Google Cloud Speech-to-Text.

1. Create a voice message detector in the message handler:
   - Identify when a message contains voice content
   - Extract necessary metadata (file_id, duration, etc.)

2. Implement a file download utility:
   - Get file path from Telegram
   - Download voice file
   - Prepare for transcription

3. Set up Google Cloud Speech-to-Text integration:
   - Client initialization with credentials from config
   - Configure for Persian language recognition
   - Implement transcription function

4. Create a processing pipeline:
   - Detect voice → Download → Transcribe → Continue to text processing
   - Handle timeouts and errors

5. Add appropriate error handling:
   - Network errors during download
   - API errors during transcription
   - User-friendly error messages in Persian

6. Write tests for:
   - Voice detection
   - File download (with mocking)
   - Transcription (with mocked API)
   - Error scenarios

Make sure to handle the API costs efficiently by validating file size and duration before processing.
```


### Step 5: LangGraph Setup

```
# LangGraph Integration for Conversation Flow

Let's set up the LangGraph framework that will manage the conversational flow of our bot.

1. Create a basic LangGraph structure:
   - Define state schema with user context, conversation memory, current intent
   - Create initial node definitions for message handling
   - Set up state transitions

2. Implement core graph nodes:
   - message_received (entry point)
   - determine_message_type (text vs. voice)
   - message_router (based on content/intent)
   - response_formatter (prepares messages for Telegram)

3. Create conversation memory management:
   - Track recent messages for context
   - Store conversation state
   - Handle session timeouts

4. Connect LangGraph to Telegram bot:
   - Forward incoming messages to graph
   - Send graph responses back to Telegram
   - Persist conversation state between messages

5. Set up error handling within the graph:
   - Track and handle exceptions
   - Route to appropriate error response
   - Allow recovery from error states

6. Write tests for:
   - Graph initialization
   - Node functionality
   - State transitions
   - Integration with Telegram handlers

The focus should be on creating a flexible structure that will support our reminder functionality in subsequent steps.
```


### Step 6: NLU - Intent Detection

```
# Natural Language Understanding - Intent Detection

Let's implement intent detection using Google Gemini API to understand what users want to do (create/view/edit/delete reminders).

1. Set up Google Gemini integration:
   - Client initialization with API key from config
   - Create API wrapper functions
   - Implement error handling and retries

2. Design prompts for Persian intent detection:
   - Create a base prompt template explaining the task
   - Add examples of different intents in Persian
   - Structure for consistent output format

3. Implement intent detection function:
   - Take message text as input
   - Format and send prompt to Gemini
   - Parse response to extract intent type
   - Return structured intent data

4. Create a LangGraph node for intent detection:
   - Process message text
   - Call intent detection function
   - Update graph state with detected intent
   - Route to appropriate next node

5. Implement the following intents:
   - create_reminder
   - view_reminders
   - edit_reminder
   - delete_reminder
   - general_conversation

6. Write tests for:
   - Intent detection with various Persian inputs
   - Edge cases (ambiguous requests)
   - LangGraph node integration
   - Error handling

Focus on making the prompts effective for Persian language understanding and ensuring the system can detect intents reliably.
```


### Step 7: NLU - Parameter Extraction

```
# Natural Language Understanding - Parameter Extraction

Now let's implement functionality to extract specific parameters (task, date, time) from user messages after intent detection.

1. Design specialized prompts for parameter extraction:
   - Task description extraction
   - Date extraction (handling Jalali calendar)
   - Time extraction (Persian formats)

2. Implement parameter extraction function:
   - Take message and intent as input
   - Send appropriate prompt to Gemini
   - Parse structured data from response
   - Handle partial or missing information

3. Create date/time handling utilities:
   - Convert relative time expressions in Persian
   - Parse Jalali calendar dates
   - Handle time formats and ambiguities

4. Implement a LangGraph node for parameter extraction:
   - Process message based on intent
   - Extract relevant parameters
   - Update graph state with extracted data
   - Determine next steps (confirmation, clarification)

5. Add parameter validation:
   - Check extracted parameters for validity
   - Flag missing required information
   - Format data for storage

6. Write tests for:
   - Parameter extraction with various inputs
   - Date/time parsing (absolute and relative)
   - Validation logic
   - Integration with intent detection

Focus on accurate parsing of Persian date/time expressions and proper handling of the Jalali calendar system.
```


## Phase 3: Reminder Management

### Step 8: Reminder Creation Flow

```
# Reminder Creation Flow Implementation

Let's implement the complete flow for creating reminders, from intent detection through confirmation and storage.

1. Create LangGraph nodes for the reminder creation flow:
   - reminder_intent_confirmed (entry point)
   - extract_reminder_details
   - generate_confirmation
   - handle_confirmation_response
   - handle_correction
   - save_reminder

2. Implement confirmation message generation:
   - Format task, date, and time information in Persian
   - Generate clear confirmation request
   - Include correction instructions

3. Create confirmation handling logic:
   - Detect affirmative/negative responses
   - Process correction requests
   - Handle ambiguous responses

4. Implement the correction flow:
   - Extract what needs to be changed
   - Update reminder details
   - Regenerate confirmation

5. Create reminder storage function:
   - Check user's subscription limits
   - Save reminder to database
   - Update reminder count

6. Write tests for:
   - The complete creation flow
   - Confirmation handling
   - Correction scenarios
   - Subscription limit enforcement

All user interactions should be in Persian, and the system should handle the conversation naturally with appropriate feedback at each step.
```


### Step 9: Reminder Viewing Implementation

```
# Reminder Viewing Implementation

Let's implement the functionality to view existing reminders, including support for pagination if needed.

1. Create database query functions:
   - Get all active reminders for a user
   - Support filtering and sorting
   - Optimize for performance

2. Implement LangGraph nodes for viewing:
   - view_reminders_intent (entry point)
   - fetch_reminders
   - format_reminder_list
   - handle_pagination

3. Create reminder formatting functions:
   - Format individual reminders in Persian
   - Create a well-structured list
   - Support for empty results

4. Implement pagination if needed:
   - Split long lists into pages
   - Create navigation controls
   - Maintain state between interactions

5. Add filtering capabilities:
   - Parse natural language filter requests
   - Apply filters to database queries
   - Show applied filters in responses

6. Write tests for:
   - Database queries
   - Formatting functions
   - Pagination logic
   - Complete viewing flow

Ensure all output is properly formatted in Persian with Jalali calendar dates and provides a good user experience even with many reminders.
```


### Step 10: Reminder Editing Flow

```
# Reminder Editing Flow Implementation

Let's implement the functionality to edit existing reminders using natural language requests.

1. Create reminder identification function:
   - Match user description to stored reminders
   - Handle ambiguous matches
   - Request clarification when needed

2. Implement LangGraph nodes for editing:
   - edit_intent_detected (entry point)
   - identify_reminder
   - extract_changes
   - confirm_changes
   - process_edit_confirmation
   - update_reminder

3. Design change extraction logic:
   - Identify what aspects to modify (task/date/time)
   - Extract new values
   - Validate changes

4. Create confirmation flow:
   - Show before/after comparison
   - Request explicit confirmation
   - Handle rejection and corrections

5. Implement database update function:
   - Update reminder fields
   - Handle validation
   - Return updated information

6. Write tests for:
   - Reminder identification
   - Change extraction
   - Confirmation handling
   - Database updates

Focus on making the editing process intuitive and handling ambiguity well when users refer to reminders in conversational language.
```


### Step 11: Reminder Deletion Flow

```
# Reminder Deletion Flow Implementation

Let's implement the functionality to delete reminders with proper confirmation.

1. Create LangGraph nodes for deletion:
   - delete_intent_detected (entry point)
   - identify_reminder_to_delete
   - confirm_deletion
   - process_deletion_confirmation
   - delete_reminder

2. Implement reminder identification:
   - Similar to editing flow
   - Match description to stored reminders
   - Handle ambiguity with clarification

3. Create confirmation workflow:
   - Generate clear confirmation message
   - Require explicit confirmation
   - Process various confirmation responses

4. Implement deletion function:
   - Remove reminder from database
   - Update user's reminder count
   - Generate confirmation message

5. Add safeguards:
   - Prevent accidental deletion
   - Allow cancellation at confirmation step
   - Provide undo functionality (optional)

6. Write tests for:
   - Reminder identification
   - Confirmation handling
   - Database operations
   - Complete deletion flow

Ensure the system never deletes reminders without explicit confirmation and handles the conversation naturally in Persian.
```


### Step 12: Notification System

```
# Notification System Implementation

Let's implement the system that will check for due reminders and send notifications to users.

1. Create a background scheduler:
   - Set up recurring task runner
   - Configure check interval
   - Handle startup/shutdown gracefully

2. Implement reminder checking logic:
   - Query for due reminders
   - Handle Jalali calendar date comparison
   - Process reminders due within 15 minutes

3. Create notification generation:
   - Format reminder messages in Persian
   - Include clear task description
   - Add appropriate context

4. Implement notification sending:
   - Send Telegram messages to users
   - Handle errors and retries
   - Update reminder status after sending

5. Add database operations:
   - Query optimization for due reminders
   - Status updates after notification
   - Handling of time zones

6. Write tests for:
   - Due reminder identification
   - Notification formatting
   - Sending mechanism
   - Scheduler operation

Ensure the


