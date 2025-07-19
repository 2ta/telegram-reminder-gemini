# TODO Checklist for Telegram Reminder Bot

## 1. Project Setup & Foundation

- [x] Set up project directory structure (`src/`, `tests/`, `resources/`, `logs/`, `config/`)
- [x] Create and populate `requirements.txt`
- [x] Implement `config/config.py` for environment variables (Pydantic)
- [x] Set up logging (Python `logging`, console + rotating file in `config/config.py`)
- [x] Write initial `README.md`
- [x] Add basic test (`tests/test_initial_setup.py`)
- [x] Ensure Python 3.9 compatibility for type hints (stt.py, utils.py, nlu.py, bot.py done)

## 2. Database & Models

- [x] Design database schema (users, reminders, payments)
- [x] Implement SQLAlchemy models (`database.py`):
    - [x] `User` (telegram_id, chat_id, name, language, is_premium, premium_until, created_at, updated_at)
    - [x] `Reminder` (user_db_id, telegram_user_id, chat_id, task_description, due_datetime_utc, recurrence_rule, is_active, is_sent, created_at, updated_at)
    - [x] `Payment` (user_db_id, track_id, amount, status, ref_id, payment_date, created_at, updated_at)
    - [x] Refined Reminder-User relationship (ForeignKey from `Reminder.user_db_id` to `User.id`)
    - [ ] Define `SubscriptionTier` model/enum and link to `User` (if more complex than `is_premium` boolean)
- [x] Create DB connection/session utilities (`database.py` -> `get_db`, `init_db`)
- [ ] Write comprehensive unit tests for models and CRUD operations (`tests/test_database.py`)

## 3. Telegram Bot Core (`src/bot.py`)

- [x] Initialize Telegram bot (`Application.builder`)
- [x] Implement `/start`, `/help` commands (Persian)
- [x] Implement `/privacy` command (Persian, display privacy policy)
- [x] Implement user registration/update on `/start` (saves/updates `User` in DB)
- [x] Implement main message handler (`handle_message`) for routing and NLU entry
- [x] Implement voice message handler (`handle_voice`) with STT and NLU entry
- [x] Implement `ConversationHandler` for multi-step reminder creation/editing
- [x] Implement `CallbackQueryHandler` (`button_callback`) for inline button interactions
- [ ] Add test coverage for handlers and user logic (`tests/test_bot.py`)

## 4. Voice Message Support

- [x] Detect and handle incoming Telegram voice messages (`bot.py` -> `handle_voice`)
- [x] Download and prepare voice files for transcription (`bot.py` -> `handle_voice` using `tempfile`)
- [x] Integrate Google Cloud Speech-to-Text (`stt.py` -> `transcribe_voice_persian`)
- [x] Handle STT errors (within `stt.py` and `bot.py`)
- [ ] Unit test voice processing logic (mocking APIs) (`tests/test_stt.py`)

## 5. Core Logic & LangGraph Integration (High Priority - Architectural Shift)

- [ ] **Architect bot flows using LangGraph with Gemini for intent processing and task execution.**
    - [x] Define core `GraphState` (`src/graph_state.py`) to manage conversational context (user info, NLU results, history, current step, etc.).
    - [x] Implement initial NLU node in LangGraph (`src/graph_nodes.py`) using Gemini (`determine_intent_node`) for intent classification and parameter extraction.
    - [~] Develop basic action nodes for simple commands (e.g., `/start`, `/help`) within the graph structure. (e.g. `execute_start_command_node` is present)
    - [~] Refactor `bot.py` (`handle_message`, `handle_voice`) to delegate primary input processing to the LangGraph executor.
        - [x] Refactor `CommandHandler`s (`/start`, `/help`, `/pay`, `/reminders` entry) to initialize `AgentState` and invoke LangGraph.
        - [x] Refactor `CallbackQueryHandler` (`button_callback`) to parse `callback_data`, initialize `AgentState`, and invoke LangGraph.
        - [x] Refactor simulated Zibal webhook (`/callback` command) to extract parameters, initialize `AgentState`, and invoke LangGraph for payment processing.
        - [x] Ensure `main()` in `bot.py` registers the refactored handlers correctly.
    - [ ] Design and implement LangGraph flow for reminder creation (replacing existing `ConversationHandler`):
        - [x] Node: Initial NLU for reminder intent (`determine_intent_node`).
        - [x] Nodes: Clarification for missing task, date, time, AM/PM (if needed) (`validate_and_clarify_reminder_node`, `determine_intent_node` for callback, `handle_intent_node` for messaging).
        - [x] Node: Confirmation of reminder details with user (`confirm_reminder_details_node`, `handle_intent_node` for messaging).
        - [x] Node: Save reminder to DB (calling `save_or_update_reminder_in_db` - done by `create_reminder_node`).
        - [x] Node: Send response to user (`handle_intent_node`).
    - [ ] Integrate reminder viewing (`list_reminders_entry`) as a LangGraph callable action/node.
        - [ ] Handle pagination and filtering parameters via graph state or node inputs.
    - [ ] Adapt reminder editing and deletion flows to be LangGraph compatible (nodes or sub-graphs).
    - [ ] Integrate Zibal payment flow (`/pay` command) as a LangGraph-managed process.
    - [ ] Ensure robust error handling and state transitions within the graph.
    - [ ] Implement conversation memory within LangGraph if complex multi-turn interactions beyond single commands are common.
    - [ ] Write specific tests for LangGraph flows, node transitions, and overall graph behavior (`tests/test_graph.py` or similar).
- [~] ~~Initial LangGraph setup (`src/graph_state.py`, `src/graph_nodes.py`) - *Currently less central...*~~ (Superseded by above)
- [ ] ~~Define graph state schema if LangGraph is expanded~~ (Superseded)
- [ ] ~~Define graph nodes for any complex sub-flows...~~ (Superseded)
- [ ] ~~Implement conversation memory if LangGraph is used more extensively~~ (Superseded by specific item above)
- [ ] ~~Write tests for any LangGraph components if their usage is expanded~~ (Superseded by specific item above)

## 6. NLU & LLM Integration

- [x] Integrate Google Gemini API for NLU (`nlu.py` -> `extract_reminder_details_gemini`)
- [x] Design Persian prompts for intent detection and parameter extraction (used in `nlu.py`)
- [x] Implement intent detection (part of `extract_reminder_details_gemini`)
- [x] Implement parameter extraction (task, date, time, recurrence - part of `extract_reminder_details_gemini`)
- [x] Handle Persian relative/Jalali dates and time parsing (`src/datetime_utils.py` -> `parse_persian_datetime_to_utc`, previously in `utils.py`)
- [ ] Test intent/parameter extraction with diverse Persian inputs (`tests/test_nlu.py`, `tests/test_datetime_utils.py`)

## 7. Reminder Management Flows (`bot.py`)

### 7.1 Creation

- [x] Implement reminder creation flow (via `ConversationHandler` states in `bot.py`)
    - [x] Detect intent, extract details (via `handle_initial_message`, `nlu.py`)
    - [x] Clarify ambiguous time (e.g., AM/PM via `AWAITING_AM_PM_CLARIFICATION` state)
    - [x] Handle default time suggestion and confirmation (via `AWAITING_TIME_ONLY` state)
    - [x] Save to DB (`save_or_update_reminder_in_db`) if confirmed and under tier limit
    - [x] Respond with confirmation or error (Persian)
- [ ] Allow natural language corrections during creation (e.g., user corrects date after bot suggests time) - *Future enhancement*
- [ ] Test all creation/correction/confirmation paths (`tests/test_bot.py` for conversation flows)

### 7.2 Viewing

- [x] Implement `/reminders` command and "یادآورهای من" button (`list_reminders_entry` in `bot.py` - now via LangGraph `handle_intent_node` for `intent_view_reminders`)
- [x] Fetch and format active reminders (Jalali date/time, Persian) (Done in LangGraph `handle_intent_node`)
- [x] Implement pagination in `list_reminders_entry` if > X (e.g., 5-10) reminders (Done in LangGraph `handle_intent_node`)
- [x] Add natural language filtering for viewing reminders (e.g., "reminders for tomorrow")
    - [x] NLU for extracting filter phrases (`nlu.py -> extract_reminder_filters_gemini`)
    - [x] Utility for resolving date phrases to ranges (`src/datetime_utils.py -> resolve_persian_date_phrase_to_range`, previously in `utils.py`)
    - [x] Bot logic to apply filters and manage state (`bot.py -> handle_filtered_list_reminders, list_reminders_entry`)
    - [x] "Clear Filters" button functionality
- [ ] Test viewing, pagination, and filtering logic

### 7.3 Editing

- [ ] Implement edit flow (entry via inline button in `list_reminders_entry`):
    - [ ] Create `ConversationHandler` for editing or expand existing one
    - [ ] State: Ask user what to edit (task, time, recurrence) via inline buttons
    - [ ] State: Receive new value for the chosen field
    - [ ] State: Validate new value (e.g., parse new date/time)
    - [ ] State: Confirm changes with the user
    - [ ] Update DB (`save_or_update_reminder_in_db`) and confirm to user (Persian)
- [ ] Handle ambiguous or unclear edit requests (clarification loop)
- [ ] Test edit scenarios (clear/ambiguous/missing info)

### 7.4 Deletion

- [x] Implement delete flow (via inline button in `list_reminders_entry`, handled in `button_callback`)
    - [x] Identify reminder to delete from callback_data
    - [x] Perform soft delete (`is_active = False`)
    - [x] Notify user (Persian)
- [ ] Add explicit confirmation step for deletion (e.g., "Are you sure? Yes/No buttons")
- [ ] Test deletion and confirmation logic

### 7.5 Notifications & Snooze

- [x] Implement background scheduler for due reminders (`check_reminders` job in `bot.py`)
- [x] Query for due reminders
- [x] Send notification messages (Persian) with snooze buttons (`check_reminders`)
- [x] Mark reminders as notified/inactive or reschedule if recurring (`check_reminders` - basic logic implemented, needs robust recurrence handling)
- [ ] Implement robust recurrence rescheduling logic in `check_reminders`
- [ ] Implement snooze functionality (`handle_snooze_request` in `bot.py`):
    - [ ] Parse reminder_id and snooze duration from callback_data
    - [ ] Update `due_datetime_utc` of the reminder in DB
    - [ ] Reset `is_sent` status
    - [ ] Confirm snooze to user
- [ ] Test notification sending, timing, recurrence, and snooze

## 8. Monetization & Subscription

- [~] Implement subscription tier logic (User model has `is_premium`, `premium_until`. Config has `MAX_REMINDERS_FREE_TIER`, `MAX_REMINDERS_PREMIUM_TIER`)
- [x] Enforce tier reminder limits on creation (`save_or_update_reminder_in_db` in `bot.py`)
- [ ] Implement `/subscription` command (show current tier, usage, expiry, upgrade options)
- [~] Integrate Zibal payment gateway:
    - [x] Payment request/URL generation (`payment.py` -> `create_payment_link`, called by `bot.py`)
    - [ ] Implement **real** Zibal webhook endpoint (e.g., `/payment/zibal_callback`):
        - [ ] Accessible publicly (needs a simple web server component or ngrok for local testing)
        - [ ] Receives `trackId` and `status` (likely GET) from Zibal after payment attempt
        - [ ] Calls `payment.py -> verify_payment(trackId)`
        - [ ] Updates DB (`Payment` table, `User.is_premium`, `User.premium_until`)
        - [ ] Notifies user of payment outcome via Telegram message (requires user_id mapping from payment)
    - [x] Payment verification logic (`payment.py` -> `verify_payment`)
    - [~] DB update and user notification on payment outcome (foundations exist in `payment.py` and `bot.py`'s simulated webhook, need integration with real webhook)
    - [ ] Store `refNumber` from Zibal in `Payment` table upon successful verification.
    - [ ] Handle Zibal API result codes robustly (consider using official numeric codes from Zibal docs).
- [ ] Test payment and subscription flows end-to-end (including real webhook if possible with ngrok)

## 9. Timezone Support

- [x] Add timezone field to User model (`src/models.py`)
- [x] Create timezone utility functions (`src/timezone_utils.py`):
    - [x] Gemini integration for city name to timezone detection
    - [x] Location-based timezone detection using ip-api.com
    - [x] Timezone validation and display name functions
    - [x] UTC conversion utilities
- [x] Implement persistent reply keyboard with Settings button (`src/bot.py`)
- [x] Add Settings menu with timezone change option
- [x] Implement location sharing for automatic timezone detection
- [x] Implement city name input for timezone detection using Gemini
- [x] Add proper keyboard navigation (back buttons, main menu)
- [x] Register location handler in application
- [ ] Test timezone functionality end-to-end
- [ ] Integrate timezone conversion in reminder creation and display

## 11. Internationalization (i18n)

- [ ] Store all user-facing strings in `config/messages.py` or similar resource files
- [ ] Refactor `bot.py` and other modules to load strings from resource files
- [ ] Architect code for potential future language support (e.g., language parameter in string loading functions)

## 12. Logging

- [x] Basic logging setup (`logging.basicConfig` in `bot.py`, configured via `config.settings`)
- [ ] Log all key events with context (user messages, NLU calls/results, DB operations, reminder notifications, payment attempts/outcomes, errors)
- [ ] For `ConversationHandler`, log state transitions and key `context.user_data` items for debugging
- [ ] Test log output, rotation, and verbosity levels

## 13. Testing (`tests/`)

- [ ] Write/expand unit tests for all modules:
    - [ ] `test_database.py`: Models, CRUD, relationships
    - [ ] `test_utils.py`: Date/time parsing, other utilities
    - [ ] `test_nlu.py`: Intent/parameter extraction (mock Gemini)
    - [ ] `test_stt.py`: Voice transcription (mock Google STT)
    - [ ] `test_payment.py`: Payment link creation, verification logic (mock Zibal API)
    - [ ] `test_bot.py`: Individual command handlers, conversation handler states, button callbacks (mock Telegram API, DB, NLU, etc.)
- [ ] Write/expand integration tests for:
    - [ ] Full reminder creation flow (text and voice)
    - [ ] Reminder viewing and listing (with pagination if implemented)
    - [ ] Reminder editing flow
    - [ ] Reminder deletion flow
    - [ ] Payment and subscription upgrade flow (mocking Zibal callback or using ngrok + test Zibal account)
    - [ ] Notification sending and snooze functionality
- [ ] Ensure good test coverage and maintainability

## 14. Error Handling & Privacy

- [~] Basic error handling in place (try-except blocks in handlers)
- [ ] Implement comprehensive user-facing error messages in Persian (from `config/messages.py`)
- [ ] Gracefully handle all exceptions in `ConversationHandler` states, API calls, and DB operations
- [ ] Ensure `/privacy` command is implemented and displays relevant privacy policy text.
- [ ] Document data handling practices and third-party API usage in `README.md` or a separate `PRIVACY.md`.

## 15. Data Retention & Privacy Compliance

- [ ] Implement automatic data retention policy for completed reminders:
    - [ ] Create background job to run daily/weekly for data cleanup
    - [ ] Delete completed reminders (`is_active = False` and `is_notified = True`) after 30 days
    - [ ] Delete manually deleted reminders (`is_active = False` and `is_notified = False`) after 30 days
    - [ ] Add configuration options for retention period (default: 30 days)
    - [ ] Log cleanup operations for audit purposes
- [ ] Implement anonymous data collection for model fine-tuning:
    - [ ] Create anonymized copy of reminder data before deletion (remove user_id, telegram_id, personal info)
    - [ ] Store anonymized data in separate table/collection for training purposes
    - [ ] Add user consent mechanism for data collection (opt-in during /start or settings)
    - [ ] Implement data export functionality for training datasets
    - [ ] Ensure GDPR compliance with right to be forgotten
- [ ] Update privacy policy to reflect data retention practices:
    - [ ] Specify 30-day retention period for completed reminders
    - [ ] Explain anonymous data collection for model improvement
    - [ ] Add user consent language for data usage
    - [ ] Include data deletion request procedures
- [ ] Add data management commands for users:
    - [ ] `/export_data` - Export user's reminder data
    - [ ] `/delete_account` - Delete all user data (with confirmation)
    - [ ] `/privacy_settings` - Manage data collection preferences
- [ ] Test data retention and cleanup functionality:
    - [ ] Unit tests for cleanup logic
    - [ ] Integration tests for anonymization process
    - [ ] Verify data deletion compliance

---


