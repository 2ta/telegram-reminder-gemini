import logging
import os
import tempfile
import datetime
import pytz
import re
import asyncio
from typing import Dict, Any, Tuple

from telegram import Update, ReplyKeyboardRemove, ForceReply, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from sqlalchemy.orm import Session

from config import * 
from database import init_db, get_db, Reminder
from stt import transcribe_voice_persian
from nlu import extract_reminder_details_gemini
from utils import parse_persian_datetime_to_utc, format_jalali_datetime_for_display, normalize_persian_numerals

# Simple logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
(
    AWAITING_TASK_DESCRIPTION, 
    AWAITING_FULL_DATETIME,    
    AWAITING_TIME_ONLY,        
    AWAITING_AM_PM_CLARIFICATION,
    AWAITING_DELETE_NUMBER_INPUT,
    AWAITING_EDIT_FIELD_CHOICE,
    AWAITING_EDIT_FIELD_VALUE,
) = range(7)

# Basic diagnostic help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help.")
    await update.message.reply_text(MSG_HELP)

# Start command handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot.")
    keyboard = [
        ["یادآورهای من", "راهنما"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(MSG_WELCOME, reply_markup=reply_markup)
    return ConversationHandler.END

# Simple echo handler
async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    text = update.message.text
    logger.info(f"User {update.effective_user.id} sent text: '{text}'")
    
    if text == "راهنما":
        await update.message.reply_text(MSG_HELP)
    elif text == "یادآورهای من":
        await update.message.reply_text("در حال حاضر یادآوری فعالی ندارید.")
    else:
        # Try to process as a reminder
        nlu_data = extract_reminder_details_gemini(text, current_context="initial_contact")
        if nlu_data and nlu_data.get("intent") == "set_reminder" and nlu_data.get("task"):
            logger.info(f"Detected reminder intent. Task: {nlu_data.get('task')}")
            
            # Check if we have all needed info
            if nlu_data.get("date") and nlu_data.get("time"):
                await update.message.reply_text(f"باشه، یادآوری تنظیم شد.\n📝 متن: {nlu_data.get('task')}\n⏰ زمان: {nlu_data.get('date')}، ساعت {nlu_data.get('time')}")
            else:
                await update.message.reply_text(f"متوجه شدم که میخواهی یادآوری برای «{nlu_data.get('task')}» تنظیم کنی. چه زمانی؟")
        else:
            # Just echo back
            await update.message.reply_text(f"پیام شما: {text}")

# Simple voice message handler
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages."""
    logger.info(f"User {update.effective_user.id} sent voice message.")
    
    # Show processing message
    await update.message.reply_text(MSG_PROCESSING_VOICE)
    
    try:
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as temp_audio_file:
            await voice_file.download_to_drive(custom_path=temp_audio_file.name)
            temp_audio_file_path = temp_audio_file.name
            
        # Try to transcribe
        transcribed_text = transcribe_voice_persian(temp_audio_file_path)
        
        # Clean up
        try: 
            os.remove(temp_audio_file_path)
        except Exception as e: 
            logger.error(f"Error deleting temp file: {e}")
            
        if transcribed_text:
            await update.message.reply_text(f"پیام صوتی شما: «{transcribed_text}»")
            
            # Now try NLU
            nlu_data = extract_reminder_details_gemini(transcribed_text, current_context="voice_transcription")
            if nlu_data and nlu_data.get("intent") == "set_reminder" and nlu_data.get("task"):
                await update.message.reply_text(f"متوجه شدم که میخواهی یادآوری برای «{nlu_data.get('task')}» تنظیم کنی.")
            else:
                await update.message.reply_text("متوجه نشدم. لطفاً دوباره تلاش کنید.")
        else:
            await update.message.reply_text(MSG_STT_FAILED)
    except Exception as e:
        logger.error(f"Error processing voice: {e}", exc_info=True)
        await update.message.reply_text("خطایی رخ داد. لطفاً دوباره تلاش کنید.")

def main() -> None:
    """Start the bot."""
    # Initialize dependencies
    try:
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)
    
    # Check for token
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN not found! Exiting.")
        return

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add simple handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))
    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, voice_handler))

    # Start the Bot
    logger.info("Starting bot in polling mode...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()