<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Can you make a `todo.md` that I can use as a checklist? Be thorough.

```markdown
# TODO Checklist for Telegram Reminder Bot (Phase 1)

## 1. Project Setup & Foundation

- [x] Set up project directory structure (`src/`, `tests/`, `resources/`, `logs/`, `config/`)
- [x] Create and populate `requirements.txt` (Python 3.9+, `python-telegram-bot`, `langgraph`, `google-cloud-speech`, `google-generativeai`, `sqlalchemy`, `alembic`, `jdatetime`, `pytest`, `python-dotenv`, `psutil`, `pydantic`, `pydantic-settings`)
- [x] Implement `config/config.py` for environment variable management (Telegram token, DB, API keys, etc.) using Pydantic
- [x] Set up logging with Python `logging` (console + rotating file handler, proper levels) in `src/logging_config.py`
- [x] Write initial `README.md` with setup and project description
- [x] Add a basic test to verify environment and test runner (`tests/test_initial_setup.py`)

## 2. Database & Models

- [x] Design database schema for users, reminders, and subscriptions
- [x] Implement SQLAlchemy models in `src/models.py`:
    - [x] User (telegram_id, name, language, tier, expiry, reminder count)
    - [x] Reminder (user_id, task, jalali_date, time, is_active, is_notified, notification_sent_at)
    - [ ] Subscription/payment tracking (for upgrades) - *Deferred until payment integration*
- [x] Create DB connection/session utilities in `src/database.py`
- [x] Write unit tests for all models and CRUD operations in `tests/test_database.py`

## 3. Telegram Bot Core

- [x] Initialize Telegram bot using `python-telegram-bot` (in `src/bot_runner.py`)
- [x] Implement `/start`, `/help`, `/privacy` commands (Persian) (in `src/bot_handlers.py`)
- [x] Implement user registration/update on first contact (in `src/bot_handlers.py` within `start_command`)
- [x] Implement basic text message handler (log messages, acknowledge) (in `src/bot_handlers.py`)
- [x] Add test coverage for handlers and user logic (in `tests/test_bot_handlers.py`)

## 4. Voice Message Support

- [x] Detect and handle incoming Telegram voice messages (in `src/bot_handlers.py` via `MessageHandler(filters.VOICE, voice_message_handler)`)
- [x] Download and prepare voice files for transcription (in `src/voice_utils.py` -> `download_voice_message`)
- [x] Integrate Google Cloud Speech-to-Text for Persian voice transcription (in `src/voice_utils.py` -> `transcribe_persian_voice`)
- [x] Handle errors (timeouts, API issues, unsupported formats) (within `src/voice_utils.py` and `src/bot_handlers.py`)
- [x] Unit test all voice processing logic (mocking APIs) (in `tests/test_voice_utils.py`)

## 5. LangGraph Integration

- [x] Set up LangGraph with state schema (user context, memory, intent, etc.) (in `src/graph_state.py`)
- [x] Define graph nodes for: (in `src/graph_nodes.py`)
    - [x] Message reception (`entry_node`)
    - [x] Message type detection (text/voice) (handled before graph or by `entry_node` implicitly)
    - [x] Routing by intent (`determine_intent_node` and `route_after_intent_determination`)
    - [x] Response formatting (`format_response_node`)
- [x] Implement conversation memory management (via `SqliteSaver` checkpointer and `add_messages` in `src/graph.py` and `src/graph_state.py`)
- [x] Integrate LangGraph with Telegram handlers (in `src/bot_handlers.py` using `invoke_graph_with_input`)
- [x] Write tests for graph structure and transitions (basic tests in `tests/test_graph.py`)

## 6. NLU & LLM Integration

- [ ] Integrate Google Gemini API for NLU
- [ ] Design Persian prompts for intent detection (create/view/edit/delete reminder)
- [ ] Implement intent detection node in LangGraph
- [ ] Implement parameter extraction (task, date, time) node
- [ ] Handle Persian relative/Jalali dates and time parsing
- [ ] Test intent/parameter extraction with various Persian inputs

## 7. Reminder Management Flows

### 7.1 Creation

- [ ] Implement reminder creation flow in LangGraph:
    - [ ] Detect intent, extract details, confirm with user (Persian)
    - [ ] Allow natural language corrections (loop until confirmed)
    - [ ] Save to DB if confirmed and under tier limit
    - [ ] Respond with confirmation or error (Persian)
- [ ] Test all creation/correction/confirmation paths

### 7.2 Viewing

- [ ] Implement `/reminders` command and natural language triggers
- [ ] Fetch and format active reminders (Jalali date/time, Persian)
- [ ] Implement pagination if >10 reminders
- [ ] Test viewing and pagination logic

### 7.3 Editing

- [ ] Implement edit flow (detect target reminder, extract changes, confirm)
- [ ] Handle ambiguous or unclear edit requests (clarification loop)
- [ ] Update DB and confirm to user (Persian)
- [ ] Test edit scenarios (clear/ambiguous/missing info)

### 7.4 Deletion

- [ ] Implement delete flow (identify reminder, ask for explicit confirmation)
- [ ] Delete from DB on confirmation, notify user (Persian)
- [ ] Test deletion and confirmation logic

### 7.5 Notifications

- [ ] Implement background scheduler for due reminders
- [ ] Query and send notification messages (Persian) at correct Jalali date/time
- [ ] Mark reminders as notified
- [ ] Test notification sending and timing

## 8. Monetization & Subscription

- [ ] Implement subscription tier logic (Free, Standard, Premium)
- [ ] Enforce tier reminder limits on creation
- [ ] Implement `/subscription` command (show tier, usage, expiry, upgrade options)
- [ ] Integrate Zibal payment gateway:
    - [ ] Payment request/URL generation
    - [ ] Payment callback/webhook
    - [ ] Payment verification
    - [ ] Update DB and notify user on success/failure
- [ ] Test payment and subscription flows

## 9. Internationalization (i18n)

- [ ] Store all user-facing strings in resource files for Persian
- [ ] Architect code for future language support

## 10. Logging

- [ ] Log all key events (user messages, NLU, DB ops, notifications, payments, errors)
- [ ] Log LangGraph state transitions and memory (for debugging)
- [ ] Ensure logs contain context (user ID, orderId, etc.)
- [ ] Test log output and rotation

## 11. Testing

- [ ] Write unit tests for all modules (LangGraph nodes, helpers, DB, payment, etc.)
- [ ] Write integration tests for:
    - [ ] Reminder creation (end-to-end)
    - [ ] Editing/deletion flows
    - [ ] Payment/upgrade flow
    - [ ] Conversational memory
- [ ] Mock external APIs (Google, Zibal) in tests
- [ ] Ensure good coverage and maintainability

## 12. Error Handling & Privacy

- [ ] Implement user-facing error messages as per spec (Persian)
- [ ] Handle all exceptions in LangGraph and handlers gracefully
- [ ] Implement `/privacy` command with policy link
- [ ] Document data handling and third-party usage

---


