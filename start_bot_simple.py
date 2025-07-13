#!/usr/bin/env python3
"""
Simple bot startup script.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import signal
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config.config import settings
from src.bot import start_command, payment_command, privacy_command, handle_stripe_webhook, handle_message, handle_voice, button_callback, ping
from src.database import init_db

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to handle shutdown
running = True

def signal_handler(signum, frame):
    global running
    logger.info(f'Received signal {signum}. Shutting down...')
    running = False

async def main():
    """Run bot with proper shutdown handling"""
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    init_db()
    
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("pay", payment_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("stripe_webhook", handle_stripe_webhook))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Starting bot...")
    
    # Initialize and start
    await application.initialize()
    await application.start()
    
    # Start polling
    await application.updater.start_polling()
    
    logger.info("✅ Bot is running! Send /ping to test.")
    
    # Keep running until signal received
    try:
        while running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        running = False
    
    logger.info("Stopping bot...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("Bot stopped successfully")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot stopped by user')
    except Exception as e:
        logger.error(f'Failed to start bot: {e}')
        sys.exit(1) 