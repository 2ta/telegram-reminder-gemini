# Telegram Reminder Bot (Gemini + LangGraph)

A Persian-language Telegram bot for setting reminders, powered by Google's Gemini AI and structured with LangGraph.

## Project Goals

- Natural language understanding for creating, viewing, editing, and deleting reminders in Persian.
- Support for voice messages.
- Jalali calendar support for dates.
- Subscription tiers with payment integration.

## Setup

1.  Clone the repository:
    ```bash
    git clone <repository_url>
    cd telegram-reminder-bot
    ```
2.  Create a virtual environment and activate it:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Set up environment variables:
    - Copy `.env.sample` to `.env`
    - Fill in your `TELEGRAM_BOT_TOKEN` and other necessary API keys/credentials.
    ```bash
    cp env.sample .env
    # Edit .env with your credentials
    ```
5.  Initialize the database (if using Alembic for migrations - to be added):
    ```bash
    # alembic upgrade head 
    ```
6.  Run the bot:
    ```bash
    python src/main.py # Or however the main entry point will be structured
    ```

## Project Structure (Planned)

- `src/`: Main application source code.
  - `main.py`: Bot entry point.
  - `bot/`: Telegram bot interaction logic.
  - `nlu/`: Natural Language Understanding (Gemini integration).
  - `voice/`: Voice processing (Speech-to-Text).
  - `db/`: Database models and interactions.
  - `graph/`: LangGraph conversational flow definition.
  - `scheduler/`: Reminder notification scheduling.
  - `payment/`: Payment gateway integration.
  - `utils/`: Common utility functions.
- `config/`: Configuration files (`config.py`).
- `resources/`: Language strings, prompts, etc.
- `tests/`: Unit and integration tests.
- `logs/`: Application logs.
- `migrations/`: Alembic database migration scripts (if Alembic is used).
- `docs/`: Project documentation.
  - `specs/`: Technical specifications.
  - `planning/`: Project planning and development tracking.
  - `testing/`: Test scenarios and documentation.

## Contributing

(Details to be added)

## License

(Details to be added) 