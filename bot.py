import logging
import os
import tempfile
import datetime
import pytz
import re
import gc  # Garbage collection for memory management
from typing import Dict, Any, Tuple

# Import only what we need from telegram to reduce memory usage
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from sqlalchemy.orm import Session

from config import * 
from database import init_db, get_db, Reminder
from stt import transcribe_voice_persian
from nlu import extract_reminder_details_gemini
from utils import parse_persian_datetime_to_utc, format_jalali_datetime_for_display, normalize_persian_numerals

# Simple logging with file backup but minimal memory usage
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        # File handler for persistent logs
        logging.FileHandler(filename='logs/bot.log', mode='a', encoding='utf-8'),
        # Console handler
        logging.StreamHandler()
    ]
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

# Memory monitoring function to help prevent OOM kills
def log_memory_usage(context_info: str = ""):
    """Log current memory usage to help diagnose OOM issues"""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024
        logger.info(f"Memory usage {context_info}: {mem_mb:.2f}MB (RSS)")
        
        # Force garbage collection if memory exceeds threshold
        if mem_mb > 500:  # 500MB threshold
            logger.warning(f"High memory usage detected ({mem_mb:.2f}MB). Running garbage collection...")
            gc.collect()
            
    except ImportError:
        logger.warning("psutil not installed - can't monitor memory usage")
    except Exception as e:
        logger.error(f"Error monitoring memory: {e}")

# Basic command handlers
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help.")
    await update.message.reply_text(MSG_HELP)
    log_memory_usage("after help command")

# Start command handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot.")
    keyboard = [
        ["یادآورهای من", "راهنما"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(MSG_WELCOME, reply_markup=reply_markup)
    log_memory_usage("after start command")
    return ConversationHandler.END

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages for setting reminders."""
    if not update.message:
        return
        
    text = update.message.text
    user_id = update.effective_user.id
    logger.info(f"User {user_id} sent text: '{text}'")
    
    if text == "راهنما":
        await update.message.reply_text(MSG_HELP)
        return
        
    if text == "یادآورهای من":
        await update.message.reply_text("در حال حاضر یادآوری فعالی ندارید.")
        return
        
    # Try to extract reminder details
    try:
        nlu_data = extract_reminder_details_gemini(text, current_context="initial_contact")
        log_memory_usage("after NLU processing")
        
        if nlu_data and nlu_data.get("intent") == "set_reminder" and nlu_data.get("task"):
            task = nlu_data.get("task")
            date = nlu_data.get("date", "")
            time = nlu_data.get("time", "")
            
            # If we have both date and time, confirm the reminder
            if date and time:
                await update.message.reply_text(
                    f"باشه، یادآوری تنظیم شد.\n📝 متن: {task}\n⏰ زمان: {date}، ساعت {time}"
                )
            # If we only have task, ask for date/time
            else:
                await update.message.reply_text(
                    f"متوجه شدم که میخواهی یادآوری برای «{task}» تنظیم کنی. چه زمانی؟"
                )
        else:
            # Just acknowledge the message
            await update.message.reply_text(f"پیام شما دریافت شد. برای تنظیم یادآوری لطفاً زمان و موضوع را مشخص کنید.")
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text("مشکلی در پردازش پیام شما رخ داد. لطفاً دوباره تلاش کنید.")
        
    # Force garbage collection after processing
    gc.collect()

# Voice message handler
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Memory-efficient voice message handler"""
    if not update.message or not update.message.voice:
        return
        
    user_id = update.effective_user.id
    logger.info(f"User {user_id} sent voice message.")
    
    # Show processing message
    await update.message.reply_text(MSG_PROCESSING_VOICE)
    
    try:
        # Download the voice file with memory monitoring
        voice_file = await update.message.voice.get_file()
        log_memory_usage("after getting voice file")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as temp_audio_file:
            await voice_file.download_to_drive(custom_path=temp_audio_file.name)
            temp_audio_file_path = temp_audio_file.name
            
        log_memory_usage("after downloading voice")
        
        # Transcribe the voice message
        transcribed_text = transcribe_voice_persian(temp_audio_file_path)
        
        # Clean up temporary file immediately
        try:
            os.remove(temp_audio_file_path)
        except Exception as e:
            logger.error(f"Error deleting temp file: {e}")
            
        log_memory_usage("after transcription")
        
        if transcribed_text:
            # Show the transcription
            await update.message.reply_text(f"پیام صوتی شما: «{transcribed_text}»")
            
            # Process the transcription with NLU - with memory limits
            try:
                nlu_data = extract_reminder_details_gemini(transcribed_text, current_context="voice_transcription")
                log_memory_usage("after NLU processing voice")
                
                if nlu_data and nlu_data.get("intent") == "set_reminder" and nlu_data.get("task"):
                    task = nlu_data.get("task")
                    date = nlu_data.get("date", "")
                    time = nlu_data.get("time", "")
                    
                    # If we have both date and time, confirm the reminder
                    if date and time:
                        await update.message.reply_text(
                            f"باشه، یادآوری تنظیم شد.\n📝 متن: {task}\n⏰ زمان: {date}، ساعت {time}"
                        )
                    # If we only have task, ask for date/time
                    else:
                        await update.message.reply_text(
                            f"متوجه شدم که میخواهی یادآوری برای «{task}» تنظیم کنی. چه زمانی؟"
                        )
                else:
                    await update.message.reply_text("متوجه نشدم دقیقاً چه یادآوری می‌خواهید تنظیم کنید. لطفاً واضح‌تر بگویید.")
            except Exception as nlu_error:
                logger.error(f"Error in NLU processing: {nlu_error}")
                await update.message.reply_text("خطا در پردازش متن. لطفاً دوباره تلاش کنید.")
        else:
            await update.message.reply_text(MSG_STT_FAILED)
    except Exception as e:
        logger.error(f"Error processing voice: {e}")
        await update.message.reply_text("مشکلی در پردازش پیام صوتی شما رخ داد. لطفاً دوباره تلاش کنید.")
    
    # Force garbage collection after voice processing
    gc.collect()

def main() -> None:
    """Start the bot with memory optimization."""
    # Log initial memory usage
    log_memory_usage("bot startup")
    
    # Initialize dependencies with memory monitoring
    try:
        init_db()
        logger.info("Database initialized.")
        log_memory_usage("after DB init")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    
    # Check for token
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN not found! Exiting.")
        return
    
    # Garbage collect before creating the application
    gc.collect()
    
    # Create application with minimal polling setup
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add basic handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice))
    
    # Log memory usage before starting polling
    log_memory_usage("before starting polling")

    # Start the Bot with memory-efficient settings
    # Using only supported parameters
    logger.info("Starting bot in polling mode...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        # Add psutil to requirements.txt
        import psutil
    except ImportError:
        logger.warning("psutil not available. Memory monitoring will be disabled.")
        logger.warning("Install with: pip install psutil")
    
    main()