# Developer Specification: Telegram Reminder Bot Assistant (Phase 1)

**Last Updated:** May 15, 2025

## 1. Project Overview
* **Goal:** Develop a Telegram bot assistant.
* **Phase 1 Core Functionality:** Implement a Reminder Bot Agent.
* **Primary Capability:** Reminder management (create, view, edit, delete, notify).

## 2. Target Audience & Language
* **Initial Release:** Persian-speaking users.
* **Language:** The bot interface, communication, and natural language understanding (NLU) **must** be implemented for **Persian (Farsi)**. All user-facing messages below must be presented in Persian.
* **Calendar:** All dates presented to the user or parsed from user input (where applicable) must use the **Jalali calendar** system. Time display should be standard (e.g., HH:MM).
* **Design for Multi-language:** While this instance is Persian-only, the codebase **must** be architected for easy localization and future deployment of separate instances in other languages (e.g., English). Use standard internationalization (i18n) practices (e.g., string resource files).

## 3. Core Features: Reminder Agent

### 3.1. Input Methods:
* Accept user commands and instructions via standard Telegram **text messages**.
* Accept user commands and instructions via **voice messages**. Voice messages must be transcribed to text before processing.

### 3.2. Reminder Creation:
* **Detection:** The bot must analyze *every* incoming user message (text or transcribed voice) using the configured LLM (Google Gemini) for NLU to detect if the user intends to set a reminder. This will be a node within the LangGraph flow.
* **Extraction:** If reminder intent is detected, extract the task description, date, and time. Handle relative date/time expressions in Persian (e.g., "فردا ساعت ۵ عصر", "پس‌فردا", "آخر هفته").
* **Confirmation:** Before saving, explicitly confirm the extracted details with the user. The LangGraph state will hold the pending reminder details.
    * **Message:**
        ```
        "بسیار خب، آیا به شما یادآوری کنم که '[task description]' در تاریخ [Jalali Date] ساعت [Time] انجام دهید؟ لطفاً با بله/خیر پاسخ دهید یا تغییرات را اعلام کنید."
        ```
* **Correction:** Allow users to reply with natural language in Persian to correct details (e.g., "نه، ساعت ۶ عصر", "وظیفه اینه که به پدرم زنگ بزنم"). The conversational memory managed by LangGraph will ensure context is maintained.
    * Process the correction using the LLM. The LangGraph state will transition based on the outcome.
    * **If LLM is confident** it understood the correction: Update the reminder details (in the LangGraph state), save it to the database (via a dedicated node/tool call), and send a final confirmation:
        * **Message:**
            ```
            "متوجه شدم. یادآوری به‌روزرسانی و ثبت شد: [task] برای تاریخ [Jalali Date] ساعت [new time]."
            ```
    * **If LLM is not confident**: Ask the user to rephrase. The graph will loop back to await user input.
        * **Message:**
            ```
            "متوجه منظور شما برای اصلاح نشدم. لطفاً دوباره و به شکل دیگری بیان کنید."
            ```
        The bot waits for another correction attempt or a confirmation/cancelation, managed by the LangGraph flow.
* **Confirmation Response:** If the user replies "yes" (or equivalent Persian confirmation like "بله") to the initial confirmation prompt, save the reminder (via a dedicated node/tool call) and confirm:
    * **Message:**
        ```
        "بسیار خب، یادآوری ثبت شد: [task] برای تاریخ [Jalali Date] ساعت [Time]."
        ```

### 3.3. Viewing Reminders:
* **Initiation:** Allow users to request their list of active reminders via:
    * A specific command: `/reminders`
    * Natural Language requests (e.g., "یادآوری‌هام رو نشون بده", "لیست یادآوری‌ها"). The LLM will interpret this intent.
* **Presentation:** Display the list as simple text in a single message. Format each item clearly:
    ```
    [Task Description] - [Jalali Date] ساعت [Time]
    ```
* **Pagination:** If the number of active reminders exceeds a defined threshold (e.g., 10), paginate the results, showing a subset per message with navigation options (e.g., "صفحه ۱ از ۳", دکمه‌های `[بعدی]`, `[قبلی]`).
* **Interaction:** The list view itself does **not** contain inline buttons for editing or deleting individual reminders.

### 3.4. Editing Reminders:
* **Initiation:** Users initiate edits via **natural language** after potentially viewing their reminders list (e.g., "یادآوری 'خرید شیر' رو به فردا تغییر بده"). Conversational memory helps link this request to previously discussed reminders if applicable.
* **Processing:** The bot uses the LLM to identify the target reminder (based on task description or other context from conversation memory) and the intended modification (task, date, or time). This will be a distinct path in the LangGraph.
* **Execution/Confirmation:**
    * **If LLM is confident** about the target reminder and the change: Update the reminder in the database and confirm the change to the user:
        * **Message:**
            ```
            "بسیار خب، یادآوری به‌روزرسانی شد: [Task] اکنون برای [New Jalali Date/Time] تنظیم شده است."
            ```
    * **If LLM is not confident**: Ask the user for clarification. The graph routes to a clarification state.
        * **Message:**
            ```
            "نتوانستم تشخیص دهم کدام یادآوری را ویرایش کنم یا چه چیزی را تغییر دهم. لطفاً دقیق‌تر بفرمایید."
            ```

### 3.5. Deleting Reminders:
* **Initiation:** Users initiate deletion via **natural language** (e.g., "یادآوری 'جلسه' رو حذف کن").
* **Processing:** The bot uses the LLM to identify the target reminder.
* **Confirmation:** **Crucially**, before deleting, the bot *must* ask for explicit confirmation:
    * **Message:**
        ```
        "آیا مطمئن هستید که می‌خواهید یادآوری '[Task]' را حذف کنید؟ لطفاً با بله یا خیر پاسخ دهید."
        ```
* **Execution:** If the user confirms ("yes" or "بله"), delete the reminder from the database and notify the user:
    * **Message:**
        ```
        "بسیار خب، یادآوری '[Task]' حذف شد."
        ```

### 3.6. Notifications:
* **Trigger:** When a reminder's due date and time is reached.
* **Format:** Send a simple text message to the user via Telegram:
    * **Message:** `"یادآوری: [Task description]"`
* **No actions (Snooze/Done)** are required on the notification message itself for Phase 1.

## 4. Monetization

### 4.1. Subscription Tiers:
* **Free:** Up to 2 active reminders concurrently.
* **Standard:** Up to 100 active reminders concurrently. (Billing cycle: Monthly - assumed).
* **Premium:** Unlimited active reminders. (Billing cycle: Monthly - assumed).

### 4.2. Limit Enforcement:
* When a user on a limited tier tries to create a reminder that would exceed their limit, deny the creation and send a message:
    * **Message:** `"شما به حد مجاز [X] یادآوری فعال در سطح کاربری [Tier Name] رسیده‌اید. برای افزودن یادآوری‌های بیشتر، لطفاً اشتراک خود را ارتقا دهید."`
    * Include an inline button with the text: `"مشاهده گزینه‌های اشتراک"` (This button should trigger the `/subscription` command flow).

### 4.3. Subscription Status Check:
* Implement a `/subscription` command.
* This command displays the user's current tier, the number of active reminders, the tier limit, and the subscription expiry/renewal date (if applicable).
* Provide clear buttons or options within this view to upgrade to paid tiers (e.g., buttons labeled with Tier Name and Price).

### 4.4. Payment Gateway Integration (Zibal - Iran):
* **Provider:** Zibal (https://help.zibal.ir/IPG/API/)
* **Payment Flow:**
    1.  User selects a paid tier to upgrade/subscribe to.
    2.  **Bot Backend:** Call Zibal's `request` API endpoint (`merchant`, `amount`, unique `orderId`, `callbackUrl`, `description`).
    3.  **Bot Backend:** Receive `trackId` and `paymentUrl` from Zibal.
    4.  **Bot Frontend:** Present the `paymentUrl` to the user via an inline button with text: `"پرداخت"`.
    5.  User completes payment on Zibal.
    6.  Zibal sends POST to `callbackUrl` (`success`, `trackId`, `orderId`).
    7.  **Bot Backend (Webhook):** Receive callback.
    8.  **Bot Backend:** Call Zibal's `verify` API endpoint (`merchant`, `trackId`).
    9.  **Bot Backend:** If `verify` response `result` is `100`:
        * Update user's subscription in DB.
        * Send confirmation message: `"اشتراک شما در طرح [Tier Name] با موفقیت فعال شد. از شما متشکریم!"`
    10. **Bot Backend:** If verification fails:
        * Send failure message: `"در تأیید پرداخت شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا در صورت ادامه مشکل با پشتیبانی تماس بگیرید."`

## 5. Technical Specifications

* **Programming Language:** Python (specify version, e.g., 3.9+)
* **Telegram Bot Library:** `python-telegram-bot` (or specify alternative)
* **Speech-to-Text (STT):** Google Cloud Speech-to-Text API
* **Natural Language Understanding (NLU) & Core Logic LLM:** Google Gemini API
    * **Model:** `gemini-2.0-flash` (Verify availability and exact name; use `gemini-1.5-flash` if 2.0 is unavailable/more suitable for conversational tasks).
    * **Prompting:** Design prompts for Persian intent recognition (reminder create, view, edit, delete), data extraction (task, date, time - including relative/Jalali), correction interpretation, and general conversational understanding.
* **Agent Framework & Conversation Orchestration:** LangGraph
    * Structure the bot's logic as a stateful graph using LangGraph. Nodes in the graph will represent processing steps (e.g., receiving message, transcribing voice, NLU/LLM call for intent/extraction, confirmation, database operations via tools/functions, sending messages). Edges will represent transitions based on conditions or LLM outputs.
    * The primary "Reminder Management" functionality will be implemented as one or more graphs.
* **Conversational Memory:**
    * The application **must** implement conversational memory, managed as part of the LangGraph state.
    * This memory should retain relevant context from recent interactions (e.g., the reminder currently being confirmed or corrected, user preferences if expressed, intermediate LLM thoughts/plans if using an agentic graph).
    * The LLM (Gemini) will be utilized by LangGraph nodes to understand user messages and make decisions within the context of this memory. Memory can be a summary of past turns or a buffer of recent messages.
* **Database:** SQLite
* **ORM:** SQLAlchemy
* **Date/Time Library:** Use a library robustly supporting timezone conversions and **Jalali calendar** (e.g., `jdatetime`).

## 6. API Integration Details

* **Google Cloud STT:** Handle authentication, errors.
* **Google Gemini (via LangGraph):** LangGraph will manage calls to Gemini. Handle authentication, prompt engineering for Persian within graph nodes, manage API limits/errors.
* **Zibal:** Securely handle merchant code. Implement robust callback/verify logic. Ensure unique `orderId`.

## 7. Logging

* **Implementation:** Use Python's standard `logging` module.
* **Logged Events:** (As detailed in previous spec: user messages, NLU results, CUD ops, notifications, API calls, payments, errors). Also log LangGraph state transitions, active node, and memory contents (selectively for debugging). Log context like user ID, `orderId`, `trackId`.
* **Logging Levels:** `DEBUG`, `INFO`, `WARNING`, `ERROR`.
* **Output:** Console and Rotating Log File (`logging.handlers.RotatingFileHandler`). Configurable path, size, backups.

## 8. Testing Plan

* **Framework:** `pytest`
* **Directory Structure:** `/tests`
* **Unit Tests:** Test individual LangGraph nodes, tools, helper functions, date logic, core NLU prompt formations (mocking LLM calls), DB interactions, payment logic.
* **Integration Tests:** Test key LangGraph flows/paths:
    * End-to-end reminder setting (message -> transcribe -> graph execution -> NLU -> confirm -> correct -> save). Mock external APIs (Google, Zibal), DB, time.
    * Test conversational memory aspects (e.g., does the bot remember the task being discussed in a correction).
    * End-to-end payment flow simulation.
* **Mocking:** `unittest.mock`, `pytest-mock` for external services and DB.
* **Test Quality:** Clear, maintainable, good coverage of graph paths and states, easy to run.

## 9. Error Handling (User-Facing)

* For unexpected backend errors, provide a generic message: `"متأسفانه مشکلی پیش آمد. لطفاً بعداً دوباره تلاش کنید."`
* LangGraph's error handling capabilities should be utilized to manage exceptions within graph execution and route to appropriate user-facing error messages or fallback states.
* Log detailed errors internally.

## 10. Data Privacy

* Implement a `/privacy` command providing a link to a Privacy Policy document (URL TBD).
* Policy details: data collected (including conversational context for memory), usage, third parties (Google, Zibal), storage, rights.

## 11. Future Considerations (Design Influence)

* **Multi-language:** Code structure supports i18n for future language instances. LangGraph graphs can be designed to be language-agnostic with language-specific prompts/tools.
* **Payment Gateways:** Modular payment logic.
* **Agent Capabilities:** LangGraph is well-suited for adding new, complex capabilities as separate graphs or subgraphs.