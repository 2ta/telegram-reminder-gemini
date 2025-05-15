<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Can you make a `todo.md` that I can use as a checklist? Be thorough.

```markdown
# TODO Checklist for Telegram Reminder Bot (Phase 1)

## 1. Project Setup & Foundation

- [x] Set up project directory structure (`src/`, `tests/`, `resources/`, `logs/`, `config/`)
- [x] Create and populate `requirements.txt` (Python 3.9+, `python-telegram-bot`, `langgraph`, `google-cloud-speech`, `google-generativeai`, `sqlalchemy`, `alembic`, `jdatetime`, `pytest`, `python-dotenv`, `psutil`)
- [x] Implement `config.py` for environment variable management (Telegram token, DB, API keys, etc.)
- [ ] Set up logging with Python `logging` (console + rotating file handler, proper levels)
- [x] Write initial `README.md` with setup and project description
- [ ] Add a basic test to verify environment and test runner

## 2. Database & Models

- [ ] Design database schema for users, reminders, and subscriptions
- [ ] Implement SQLAlchemy models:
    - [ ] User (telegram_id, name, language, tier, expiry, reminder count)
    - [ ] Reminder (user_id, task, jalali_date, time, is_active, is_notified, notification_sent_at)
    - [ ] Subscription/payment tracking (for upgrades)
- [ ] Create DB connection/session utilities
- [ ] Write unit tests for all models and CRUD operations

## 3. Telegram Bot Core

- [ ] Initialize Telegram bot using `python-telegram-bot`
- [ ] Implement `/start`, `/help`, `/privacy` commands (Persian)
- [ ] Implement user registration/update on first contact
- [ ] Implement basic text message handler (log messages, acknowledge)
- [ ] Add test coverage for handlers and user logic

## 4. Voice Message Support

- [ ] Detect and handle incoming Telegram voice messages
- [ ] Download and prepare voice files for transcription
- [ ] Integrate Google Cloud Speech-to-Text for Persian voice transcription
- [ ] Handle errors (timeouts, API issues, unsupported formats)
- [ ] Unit test all voice processing logic (mocking APIs)

## 5. LangGraph Integration

- [ ] Set up LangGraph with state schema (user context, memory, intent, etc.)
- [ ] Define graph nodes for:
    - [ ] Message reception
    - [ ] Message type detection (text/voice)
    - [ ] Routing by intent
    - [ ] Response formatting
- [ ] Implement conversation memory management
- [ ] Integrate LangGraph with Telegram handlers
- [ ] Write tests for graph structure and transitions

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

**Use this checklist as a living document and check off each item as you implement and test it.**
```

<div style="text-align: center">⁂</div>

[^1]: spec.md

[^2]: spec.md

