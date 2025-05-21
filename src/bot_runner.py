import logging
import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.bot_handlers import (
    start_command, help_command, privacy_command,
    text_message_handler, voice_message_handler, error_handler
)
from config.config import settings
from src.logging_config import setup_logging
from src.database import init_db

logger = logging.getLogger(__name__)

def register_handlers(application):
    """Register all handlers for the application."""
    logger.info("Registering handlers for the application")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_error_handler(error_handler)
    # Add callback query handler for handling button clicks
    from telegram.ext import CallbackQueryHandler
    from src.bot import button_callback
    application.add_handler(CallbackQueryHandler(button_callback))

async def main():
    """Main entry point for the application."""
    setup_logging()
    logger.info(f"Starting bot with token: {settings.TELEGRAM_BOT_TOKEN[:6]}...")

    # Initialize database (create tables if needed and update schema)
    logger.info("Initializing database...")
    init_db()
    
    # Create the Application and pass it bot's token
    application = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    register_handlers(application)

    # Initialize and start the application
    logger.info("Initializing and starting the application...")
    await application.initialize()
    await application.start()

    # Start polling
    logger.info("Starting to poll")
    await application.updater.start_polling(allowed_updates=["message", "callback_query"])

    # Keep the application running until interrupted
    try:
        while True:
            await asyncio.sleep(3600) # Keep alive, or use a more sophisticated method
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Stopping updater and application...")
        if application.updater and application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot shut down gracefully.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Cannot close a running event loop" in str(e) or "This event loop is already running" in str(e):
            logger.warning(f"Event loop error during final shutdown sequence (normal on some setups): {e}")
        else:
            logger.error(f"Runtime error: {e}", exc_info=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True) 