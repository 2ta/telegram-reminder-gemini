import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config.config import settings
from src.logging_config import setup_logging
from src.database import create_tables # For initial table creation if needed
from src.bot_handlers import (
    start_command,
    help_command,
    privacy_command,
    text_message_handler,
    error_handler
)

logger = logging.getLogger(__name__)

def run_bot():
    """Initializes and runs the Telegram bot."""
    # Setup logging first
    setup_logging()
    logger.info(f"Starting bot with token: {'*' * 5 if settings.TELEGRAM_BOT_TOKEN else 'NOT SET'}")

    # Create database tables if they don't exist (optional, consider Alembic for migrations)
    # create_tables() 
    # logger.info("Database tables checked/created.")

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env file or environment variables.")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("privacy", privacy_command))

    # Register message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Register error handler
    application.add_error_handler(error_handler)

    logger.info("Bot application created and handlers registered. Starting polling...")
    # Run the bot until the user presses Ctrl-C
    application.run_polling()

    logger.info("Bot has stopped.")

if __name__ == '__main__':
    run_bot() 