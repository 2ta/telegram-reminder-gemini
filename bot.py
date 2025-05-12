import logging
import os
import tempfile
import datetime
import pytz
import re
import gc  # Garbage collection for memory management
from typing import Dict, Any, Tuple

# Import only what we need from telegram to reduce memory usage
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
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
        if mem_mb > 500:  # 500MB threshold -> Adjusted from 150MB, consider server capacity
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

async def save_or_update_reminder_in_db(user_id: int, chat_id: int, context_data: Dict[str, Any], reminder_id_to_update: int | None = None) -> Tuple[Reminder | None, str | None]:
    task = context_data.get('task')
    date_str = context_data.get('date_str')
    time_str = context_data.get('time_str')
    recurrence = context_data.get('recurrence')

    error_msg = None
    if not task: error_msg = "موضوع یادآور مشخص نشده است."
    if not date_str: error_msg = "تاریخ یادآور مشخص نشده است."
    if not time_str: error_msg = "زمان یادآور مشخص نشده است."
    if error_msg:
        logger.error(f"Save attempt with incomplete data: {error_msg} - Data: {context_data}")
        return None, error_msg

    due_datetime_utc = parse_persian_datetime_to_utc(date_str, time_str)
    if not due_datetime_utc:
        logger.error(f"Failed to parse date='{date_str}' time='{time_str}' in save_or_update_reminder_in_db")
        return None, MSG_DATE_PARSE_ERROR
    
    if due_datetime_utc < datetime.datetime.now(pytz.utc) and not recurrence:
        logger.warning(f"Attempt to save non-recurring reminder in past: {due_datetime_utc}")
        jalali_date_display, time_display_parsed = format_jalali_datetime_for_display(due_datetime_utc)
        return None, MSG_REMINDER_IN_PAST.format(date=jalali_date_display, time=time_display_parsed)

    db = next(get_db())
    try:
        if reminder_id_to_update:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id_to_update, Reminder.user_id == user_id).first()
            if not reminder:
                return None, MSG_REMINDER_NOT_FOUND_FOR_ACTION
            action = "updated"
        else:
            reminder = Reminder(user_id=user_id, chat_id=chat_id, is_active=True)
            db.add(reminder)
            action = "saved"
        
        reminder.task_description = task
        reminder.due_datetime_utc = due_datetime_utc
        reminder.recurrence_rule = recurrence
        reminder.is_sent = False 

        db.commit()
        db.refresh(reminder)
        logger.info(f"Reminder ID {reminder.id} {action}: User {user_id}, Task '{task}', Due {due_datetime_utc}, Rec: {recurrence}")
        return reminder, None
    except Exception as e:
        db.rollback()
        logger.error(f"Error {action} reminder in DB: {e}", exc_info=True)
        return None, MSG_GENERAL_ERROR
    finally:
        db.close()
        log_memory_usage(f"after DB {action}")
        gc.collect()

async def handle_initial_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text.strip()
    context.user_data.clear()
    log_memory_usage(f"initial message from {user_id}")
    logger.info(f"User {user_id} initial message: '{text}'")

    # Check for list reminders button press or /list command - this should be handled by a separate handler ideally
    # For now, let's keep it simple and not transition to a conv state here for list.
    if text == "یادآورهای من":
        # This will be handled by list_reminders_entry directly now
        return ConversationHandler.END
    if text == "راهنما":
        await update.message.reply_text(MSG_HELP)
        return ConversationHandler.END

    # Regular reminder processing continues below
    nlu_data = extract_reminder_details_gemini(text, current_context="initial_contact")
    log_memory_usage(f"after NLU for {user_id}")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return ConversationHandler.END

    intent = nlu_data.get("intent")
    context.user_data['nlu_data'] = nlu_data
    context.user_data['task'] = nlu_data.get("task")
    context.user_data['date_str'] = nlu_data.get("date")
    context.user_data['time_str'] = nlu_data.get("time")
    context.user_data['recurrence'] = nlu_data.get("recurrence")
    context.user_data['am_pm'] = nlu_data.get("am_pm")

    if intent == "set_reminder":
        # Scenario 1 start: Only task given
        if context.user_data['task'] and not context.user_data['date_str'] and not context.user_data['time_str']:
            logger.info(f"Intent: set_reminder. Task given, date/time missing. Asking for datetime.")
            await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
            return AWAITING_FULL_DATETIME

        # Scenario: Task and Date given, Time missing (e.g. "فردا یادم بنداز X")
        elif context.user_data['task'] and context.user_data['date_str'] and not context.user_data['time_str']:
            logger.info(f"Intent: set_reminder. Task & Date given, Time missing. Setting default 09:00.")
            context.user_data['time_str'] = "09:00" # Default time

            reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
            if error:
                await update.message.reply_text(error)
                return ConversationHandler.END
            if reminder:
                jalali_date, _ = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                context.user_data['last_reminder_id_for_time_update'] = reminder.id
                await update.message.reply_text(MSG_CONFIRM_DEFAULT_TIME.format(task=reminder.task_description, date=jalali_date))
                return AWAITING_TIME_ONLY

        # Scenario 3 & 4: All parts present (task, date, time)
        elif context.user_data['task'] and context.user_data['date_str'] and context.user_data['time_str']:
            if nlu_data.get("raw_time_input") and not context.user_data['am_pm']:
                 ambiguous_hour_match = re.match(r"(\\d{1,2})", context.user_data['time_str'])
                 if ambiguous_hour_match:
                    ambiguous_hour = int(ambiguous_hour_match.group(1))
                    logger.info(f"Time {context.user_data['time_str']} from NLU is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
                    context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
                    await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=context.user_data['ambiguous_time_hour_str']))
                    return AWAITING_AM_PM_CLARIFICATION

            reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
            if error:
                await update.message.reply_text(error)
                return ConversationHandler.END
            if reminder:
                jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
                await update.message.reply_text(MSG_CONFIRMATION.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
                return ConversationHandler.END
        else:
            logger.info(f"Intent: set_reminder, but not enough initial parts. Asking for task if missing, else datetime.")
            if not context.user_data['task']:
                await update.message.reply_text(MSG_REQUEST_TASK)
                return AWAITING_TASK_DESCRIPTION
            else:
                 await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
                 return AWAITING_FULL_DATETIME
    else:
        logger.info(f"NLU intent '{intent}' not directly handled as entry or is unclear. Defaulting to failure message.")
        await update.message.reply_text(MSG_FAILURE_EXTRACTION)
        return ConversationHandler.END

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    log_memory_usage(f"received_task_description from {update.effective_user.id}")
    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_task_description")
    log_memory_usage(f"after NLU for received_task_description from {update.effective_user.id}")

    if nlu_data and nlu_data.get("intent") == "provide_task" and nlu_data.get("task"):
        context.user_data['task'] = nlu_data.get("task")
        logger.info(f"User {update.effective_user.id} provided task: {context.user_data['task']}. Asking for datetime.")
        await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
        return AWAITING_FULL_DATETIME
    elif nlu_data and nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)
    else:
        await update.message.reply_text(MSG_REQUEST_TASK + " (لطفاً موضوع یادآور را بنویسید یا 'لغو' کنید)")
        return AWAITING_TASK_DESCRIPTION

async def received_full_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    log_memory_usage(f"received_full_datetime from {user_id}")
    logger.info(f"User {user_id} (state AWAITING_FULL_DATETIME) provided: '{text}' for task '{context.user_data.get('task')}'")

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_full_datetime")
    log_memory_usage(f"after NLU for received_full_datetime from {user_id}")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return AWAITING_FULL_DATETIME

    if nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)

    date_str = nlu_data.get("date")
    time_str = nlu_data.get("time")
    if nlu_data.get("recurrence"): context.user_data['recurrence'] = nlu_data.get("recurrence")
    if nlu_data.get("am_pm"): context.user_data['am_pm'] = nlu_data.get("am_pm")

    if not date_str:
        await update.message.reply_text(MSG_DATE_PARSE_ERROR + "\\n" + MSG_REQUEST_FULL_DATETIME)
        return AWAITING_FULL_DATETIME

    context.user_data['date_str'] = date_str

    if not time_str:
        logger.info(f"Date '{date_str}' provided, time missing. Setting default 09:00.")
        context.user_data['time_str'] = "09:00"
        reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
        if error:
            await update.message.reply_text(error)
            return ConversationHandler.END
        if reminder:
            jalali_date, _ = format_jalali_datetime_for_display(reminder.due_datetime_utc)
            context.user_data['last_reminder_id_for_time_update'] = reminder.id
            await update.message.reply_text(MSG_CONFIRM_DEFAULT_TIME.format(task=context.user_data['task'], date=jalali_date))
            return AWAITING_TIME_ONLY
    else:
        context.user_data['time_str'] = time_str
        if nlu_data.get("raw_time_input") and not nlu_data.get("am_pm"):
            ambiguous_hour_match = re.match(r"(\\d{1,2})", time_str)
            if ambiguous_hour_match:
                ambiguous_hour = int(ambiguous_hour_match.group(1))
                logger.info(f"Time {time_str} from NLU is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
                context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
                await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=str(ambiguous_hour)))
                return AWAITING_AM_PM_CLARIFICATION

        reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
        if error:
            await update.message.reply_text(error)
            return ConversationHandler.END
        if reminder:
            jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
            rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
            await update.message.reply_text(MSG_CONFIRMATION.format(task=context.user_data['task'], date=jalali_date, time=time_disp, recurrence_info=rec_info))
    gc.collect()
    return ConversationHandler.END


async def received_time_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    log_memory_usage(f"received_time_only from {user_id}")
    logger.info(f"User {user_id} (state AWAITING_TIME_ONLY) provided: '{text}' to change time for reminder ID {context.user_data.get('last_reminder_id_for_time_update')}")

    reminder_id_to_update = context.user_data.get('last_reminder_id_for_time_update')
    if not reminder_id_to_update or not context.user_data.get('task') or not context.user_data.get('date_str'):
        await update.message.reply_text(MSG_GENERAL_ERROR + " (اطلاعات یادآور قبلی برای تغییر ساعت یافت نشد. لطفاً از ابتدا شروع کنید.)")
        return ConversationHandler.END


    if nlu_data.get("intent") not in ["provide_time", "set_reminder"] or not nlu_data.get("time"):
        await update.message.reply_text(MSG_DATE_PARSE_ERROR + " (فرمت ساعت نامفهوم است).\\n" + MSG_REQUEST_TIME_ONLY)
        return AWAITING_TIME_ONLY

    new_time_str = nlu_data.get("time")
    context.user_data['time_str'] = new_time_str
    if nlu_data.get("am_pm"): context.user_data['am_pm'] = nlu_data.get("am_pm")


    if nlu_data.get("raw_time_input") and not nlu_data.get("am_pm"):
        ambiguous_hour_match = re.match(r"(\\d{1,2})", new_time_str)
        if ambiguous_hour_match:
            ambiguous_hour = int(ambiguous_hour_match.group(1))
            logger.info(f"New time '{new_time_str}' is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
            context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
            await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=str(ambiguous_hour)))
            return AWAITING_AM_PM_CLARIFICATION

    reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data, reminder_id_to_update)
    if error:
        await update.message.reply_text(error)
        if error == MSG_DATE_PARSE_ERROR: return AWAITING_TIME_ONLY
        return ConversationHandler.END
    if reminder:
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
        rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
        await update.message.reply_text(MSG_CONFIRMATION_UPDATE.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
    gc.collect()
    return ConversationHandler.END

async def received_am_pm_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    log_memory_usage(f"received_am_pm_clarification from {user_id}")
    logger.info(f"User {user_id} (state AWAITING_AM_PM_CLARIFICATION) provided AM/PM: '{text}' for hour {context.user_data.get('ambiguous_time_hour_str')}")

    ambiguous_hour_str = context.user_data.get('ambiguous_time_hour_str')
    if not ambiguous_hour_str:
        await update.message.reply_text(MSG_GENERAL_ERROR + " (زمینه ساعت برای تعیین صبح/عصر یافت نشد)")
        return ConversationHandler.END

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_am_pm_clarification")
    log_memory_usage(f"after NLU for received_am_pm_clarification from {user_id}")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return AWAITING_AM_PM_CLARIFICATION

    if nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)

    if nlu_data.get("intent") != "provide_am_pm" or not nlu_data.get("am_pm"):
        await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=ambiguous_hour_str) + " (لطفاً فقط 'صبح'، 'ظهر' یا 'بعد از ظهر' را مشخص کنید)")
        return AWAITING_AM_PM_CLARIFICATION

    am_pm_specifier = nlu_data.get("am_pm")
    hour_12_format = int(ambiguous_hour_str)

    hour_24_format = hour_12_format
    if am_pm_specifier == "pm" and hour_12_format < 12:
        hour_24_format += 12
    elif am_pm_specifier == "am" and hour_12_format == 12: # 12 AM (midnight) -> 00
        hour_24_format = 0

    minute_str = "00"
    if context.user_data.get('time_str') and ':' in context.user_data['time_str']:
        minute_str = context.user_data['time_str'].split(':')[1]

    context.user_data['time_str'] = f"{hour_24_format:02d}:{minute_str}"
    context.user_data['am_pm'] = am_pm_specifier

    reminder_id_to_update = context.user_data.get('last_reminder_id_for_time_update')
    reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data, reminder_id_to_update)

    if error:
        await update.message.reply_text(error)
        return ConversationHandler.END
    if reminder:
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
        rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
        msg_format = MSG_CONFIRMATION_UPDATE if reminder_id_to_update else MSG_CONFIRMATION
        await update.message.reply_text(msg_format.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
    gc.collect()
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"User {user_id} cancelled conversation.")
    # Check if update.message exists before trying to reply
    if update.message:
        await update.message.reply_text(MSG_CANCELLED)
    elif update.callback_query: # Handle cancellation from callback query
        try:
            await update.callback_query.edit_message_text(MSG_CANCELLED)
        except Exception as e:
            logger.error(f"Error editing message on cancel from callback: {e}")
            # If edit fails, try sending a new message if possible (might not have chat_id easily)

    context.user_data.clear()
    if update.effective_user: # Clear bot_data related to snooze for this user too
        context.bot_data.pop(update.effective_user.id, None)
    gc.collect()
    return ConversationHandler.END

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.voice:
        return ConversationHandler.END

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    log_memory_usage(f"voice message from {user_id}")
    logger.info(f"User {user_id} sent voice message.")

    processing_msg = await update.message.reply_text(MSG_PROCESSING_VOICE)

    try:
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as temp_audio_file:
            await voice_file.download_to_drive(custom_path=temp_audio_file.name)
            temp_audio_file_path = temp_audio_file.name
        log_memory_usage(f"after voice download for {user_id}")

        transcribed_text = transcribe_voice_persian(temp_audio_file_path)
        try:
            os.remove(temp_audio_file_path)
        except OSError as e:
            logger.error(f"Error deleting temp voice file {temp_audio_file_path}: {e}")
        log_memory_usage(f"after STT for {user_id}")
        
        # Delete processing message
        if processing_msg:
            try: 
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
            except Exception as e: 
                logger.error(f"Failed to delete processing voice message: {e}")

        if not transcribed_text:
            logger.warning(f"Voice transcription failed for user {user_id}")
            await update.message.reply_text(MSG_STT_FAILED)
            return ConversationHandler.END

        logger.info(f"Transcription for user {user_id}: \"{transcribed_text}\"")
        await update.message.reply_text(f"پیام صوتی شما: «{transcribed_text}»")
        
        # Use the transcribed text like a regular message for NLU
        context.user_data.clear()
        nlu_data = extract_reminder_details_gemini(transcribed_text, current_context="voice_transcription")
        log_memory_usage(f"after NLU for voice from {user_id}")

        if not nlu_data:
            await update.message.reply_text(MSG_NLU_ERROR)
            return ConversationHandler.END

        intent = nlu_data.get("intent")
        context.user_data['nlu_data'] = nlu_data
        context.user_data['task'] = nlu_data.get("task")
        context.user_data['date_str'] = nlu_data.get("date")
        context.user_data['time_str'] = nlu_data.get("time")
        context.user_data['recurrence'] = nlu_data.get("recurrence")
        context.user_data['am_pm'] = nlu_data.get("am_pm")
        
        if intent == "set_reminder":
            if context.user_data['task'] and not context.user_data['date_str'] and not context.user_data['time_str']:
                await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
                return AWAITING_FULL_DATETIME
            elif context.user_data['task'] and context.user_data['date_str'] and not context.user_data['time_str']:
                context.user_data['time_str'] = "09:00"
                reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
                if error: await update.message.reply_text(error); return ConversationHandler.END
                if reminder:
                    jalali_date, _ = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                    context.user_data['last_reminder_id_for_time_update'] = reminder.id
                    await update.message.reply_text(MSG_CONFIRM_DEFAULT_TIME.format(task=reminder.task_description, date=jalali_date))
                    return AWAITING_TIME_ONLY
            elif context.user_data['task'] and context.user_data['date_str'] and context.user_data['time_str']:
                if nlu_data.get("raw_time_input") and not context.user_data['am_pm']:
                    ambiguous_hour_match = re.match(r"(\\d{1,2})", context.user_data['time_str'])
                    if ambiguous_hour_match:
                        ambiguous_hour = int(ambiguous_hour_match.group(1))
                        context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
                        await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=str(ambiguous_hour)))
                        return AWAITING_AM_PM_CLARIFICATION
                reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
                if error: await update.message.reply_text(error); return ConversationHandler.END
                if reminder:
                    jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                    rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
                    await update.message.reply_text(MSG_CONFIRMATION.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
                    return ConversationHandler.END
            else:
                if not context.user_data['task']:
                    await update.message.reply_text(MSG_REQUEST_TASK); return AWAITING_TASK_DESCRIPTION
                else:
                    await update.message.reply_text(MSG_REQUEST_FULL_DATETIME); return AWAITING_FULL_DATETIME
        else:
            await update.message.reply_text(MSG_FAILURE_EXTRACTION)
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR + " (خطای پردازش پیام صوتی)")
        return ConversationHandler.END
    finally:
        gc.collect()

async def display_list_and_ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    log_memory_usage(f"display_list_and_ask_delete for {user_id}")
    logger.info(f"User {user_id} requested to list reminders.")
    
    db = next(get_db())
    try:
        reminders_from_db = db.query(Reminder).filter(
            Reminder.user_id == user_id,
            Reminder.is_active == True
        ).order_by(Reminder.due_datetime_utc).all()
    finally:
        db.close()
    
    if not reminders_from_db:
        await update.message.reply_text(MSG_LIST_EMPTY)
        return ConversationHandler.END

    response_text = MSG_LIST_HEADER + "\n\n" # Added an extra newline for better spacing
    display_map = {} # To map display index to reminder ID
    keyboard_buttons = [] # For inline keyboard

    for index, reminder_obj in enumerate(reminders_from_db, 1):
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder_obj.due_datetime_utc)
        recurrence_info = f" (تکرار: {reminder_obj.recurrence_rule})" if reminder_obj.recurrence_rule else ""
        response_text += MSG_LIST_ITEM.format(
            index=index, 
            task=reminder_obj.task_description, 
            date=jalali_date, 
            time=time_disp,
            recurrence_info=recurrence_info
        ) + "\n" # Changed to simple newline instead of escaped newline
        display_map[index] = reminder_obj.id 
        # Add buttons for each reminder
        edit_button = InlineKeyboardButton(f"✏️ ویرایش #{index}", callback_data=f"edit_{reminder_obj.id}")
        delete_button = InlineKeyboardButton(f"🗑️ حذف #{index}", callback_data=f"delete_{reminder_obj.id}")
        keyboard_buttons.append([edit_button, delete_button])
    
    context.user_data['reminders_list_map'] = display_map
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    if update.callback_query:
        # If this is called from a callback query, edit the message
        await update.callback_query.edit_message_text(response_text, reply_markup=reply_markup)
    else:
        # If this is called from a command or button press, send a new message
        await update.message.reply_text(response_text, reply_markup=reply_markup)
        
    return ConversationHandler.END # Ends the current conversation if any, buttons will trigger new one or action

async def list_reminders_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /list command or 'یادآورهای من' button."""
    return await display_list_and_ask_delete(update, context)

async def received_delete_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This state might not be directly used if we rely on inline buttons for delete selection.
    # However, keeping it for potential direct number input for deletion.
    user_id = update.effective_user.id
    text = update.message.text.strip()
    log_memory_usage(f"received_delete_number_input from {user_id}")
    logger.info(f"User {user_id} (state AWAITING_DELETE_NUMBER_INPUT) response for deletion: '{text}'")

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_delete_number_input")
    if nlu_data and nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)

    selected_index = None
    if nlu_data and nlu_data.get("intent") == "delete_reminder_by_number" and nlu_data.get("extracted_number") is not None:
        selected_index = nlu_data.get("extracted_number")
    else:
        try:
            selected_index = int(normalize_persian_numerals(text) or "-1")
        except ValueError:
            pass

    reminders_map = context.user_data.get('reminders_list_map', {})
    reminder_id_to_delete = reminders_map.get(selected_index)

    if not reminder_id_to_delete:
        await update.message.reply_text(MSG_INVALID_SELECTION + "\n" + MSG_SELECT_FOR_DELETE)
        return AWAITING_DELETE_NUMBER_INPUT

    db = next(get_db())
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id_to_delete, Reminder.user_id == user_id, Reminder.is_active == True).first()
        if reminder:
            reminder.is_active = False # Soft delete
            db.commit()
            await update.message.reply_text(MSG_REMINDER_DELETED.format(task=reminder.task_description))
        else:
            await update.message.reply_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting reminder ID {reminder_id_to_delete}: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR)
    finally:
        db.close()
        log_memory_usage(f"after DB delete for {user_id}")
        gc.collect()

    context.user_data.clear()
    return ConversationHandler.END

async def handle_edit_reminder_request(update: Update, context: ContextTypes.DEFAULT_TYPE, reminder_id: int) -> int:
    log_memory_usage(f"handle_edit_reminder_request for {update.effective_user.id}")
    context.user_data.clear() # Clear previous context
    context.user_data['reminder_to_edit_id'] = reminder_id

    db = next(get_db())
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == update.effective_user.id).first()
        if not reminder:
            await update.callback_query.edit_message_text(text=MSG_REMINDER_NOT_FOUND_FOR_ACTION)
            return ConversationHandler.END
        context.user_data['current_task_for_edit'] = reminder.task_description
        context.user_data['current_due_for_edit'] = reminder.due_datetime_utc
        context.user_data['current_recurrence_for_edit'] = reminder.recurrence_rule
    finally:
        db.close()

    keyboard = [
        [InlineKeyboardButton("📝 متن یادآور", callback_data=f"edit_field_task_{reminder_id}")],
        [InlineKeyboardButton("⏰ زمان یادآور", callback_data=f"edit_field_time_{reminder_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text=MSG_EDIT_REMINDER_FIELD_CHOICE, reply_markup=reply_markup)
    return AWAITING_EDIT_FIELD_CHOICE

async def received_edit_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data_parts = query.data.split('_')
    field_to_edit = data_parts[2]
    reminder_id = int(data_parts[3])

    log_memory_usage(f"received_edit_field_choice for {query.from_user.id}") 
    context.user_data['field_to_edit'] = field_to_edit
    # reminder_to_edit_id should already be in context from handle_edit_reminder_request via button callback
    # Ensure it is by setting it again if it came from callback data
    context.user_data['reminder_to_edit_id'] = reminder_id

    if field_to_edit == 'task':
        await query.edit_message_text(text=MSG_REQUEST_TASK + " (برای ویرایش متن فعلی، متن جدید را وارد کنید)")
    elif field_to_edit == 'time':
        await query.edit_message_text(text=MSG_REQUEST_FULL_DATETIME + " (برای ویرایش زمان فعلی، تاریخ و ساعت جدید را وارد کنید)")
    else:
        await query.edit_message_text(text="انتخاب نامعتبر.")
        return ConversationHandler.END
    return AWAITING_EDIT_FIELD_VALUE

async def received_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    log_memory_usage(f"received_edit_field_value from {user_id}")

    reminder_id = context.user_data.get('reminder_to_edit_id')
    field_to_edit = context.user_data.get('field_to_edit')

    if not reminder_id or not field_to_edit:
        await update.message.reply_text(MSG_GENERAL_ERROR + " (خطا در اطلاعات ویرایش)")
        return ConversationHandler.END

    db = next(get_db())
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == user_id).first()
        if not reminder:
            await update.message.reply_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
            return ConversationHandler.END

        if field_to_edit == 'task':
            reminder.task_description = text
            # Time and date remain the same, pull from existing reminder
            context_data_for_update = {
                'task': text,
                'date_str': format_jalali_datetime_for_display(reminder.due_datetime_utc)[0], # Get date part
                'time_str': format_jalali_datetime_for_display(reminder.due_datetime_utc)[1], # Get time part
                'recurrence': reminder.recurrence_rule
            }
        elif field_to_edit == 'time':
            nlu_data = extract_reminder_details_gemini(text, current_context="editing_reminder_time")
            log_memory_usage(f"after NLU for received_edit_field_value (time) from {user_id}")
            if not nlu_data or not nlu_data.get("date") or not nlu_data.get("time"):
                await update.message.reply_text(MSG_DATE_PARSE_ERROR + "\nمجدداً تلاش کنید یا 'لغو' بفرستید.")
                return AWAITING_EDIT_FIELD_VALUE # Stay in state
            
            context_data_for_update = {
                'task': reminder.task_description, # Keep original task
                'date_str': nlu_data.get("date"),
                'time_str': nlu_data.get("time"),
                'recurrence': nlu_data.get("recurrence") or reminder.recurrence_rule # Use new if provided, else old
            }
        else:
            await update.message.reply_text("خطای داخلی: فیلد ویرایش نامشخص.")
            return ConversationHandler.END

        # Use save_or_update_reminder_in_db to update
        updated_reminder, error = await save_or_update_reminder_in_db(user_id, reminder.chat_id, context_data_for_update, reminder_id_to_update=reminder_id)
        if error:
            await update.message.reply_text(error)
            # If date parse error, maybe let them retry
            if error == MSG_DATE_PARSE_ERROR and field_to_edit == 'time': 
                return AWAITING_EDIT_FIELD_VALUE
            return ConversationHandler.END
        
        if updated_reminder:
            jalali_date, time_disp = format_jalali_datetime_for_display(updated_reminder.due_datetime_utc)
            rec_info = f" (تکرار: {updated_reminder.recurrence_rule})" if updated_reminder.recurrence_rule else ""
            await update.message.reply_text(MSG_CONFIRMATION_UPDATE.format(task=updated_reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating reminder ID {reminder_id}: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR)
    finally:
        db.close()
        log_memory_usage(f"after DB update for {user_id}")
        gc.collect()

    context.user_data.clear()
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer() # Always answer callback queries
    data = query.data
    user_id = query.from_user.id
    log_memory_usage(f"button_callback for {user_id}, data: {data}")

    # Clear any pending snooze context if user interacts with buttons
    context.bot_data.pop(user_id, None)

    if data.startswith("edit_field_task_") or data.startswith("edit_field_time_"):
        return await received_edit_field_choice(update, context) # Pass to this handler
    elif data.startswith("edit_"):
        try:
            reminder_id = int(data.split('_')[1])
            return await handle_edit_reminder_request(update, context, reminder_id)
        except (IndexError, ValueError):
            logger.error(f"Invalid callback data for edit: {data}")
            await query.edit_message_text("خطای داخلی در پردازش درخواست ویرایش.")
            return ConversationHandler.END
    elif data.startswith("delete_"):
        try:
            reminder_id_to_delete = int(data.split('_')[1])
            db = next(get_db())
            deleted_task_desc = "یادآور"
            deleted_successfully = False
            
            try:
                reminder = db.query(Reminder).filter(Reminder.id == reminder_id_to_delete, Reminder.user_id == user_id).first()
                if reminder:
                    deleted_task_desc = reminder.task_description
                    reminder.is_active = False # Soft delete
                    db.commit()
                    deleted_successfully = True
                else:
                    await query.edit_message_text(text=MSG_REMINDER_NOT_FOUND_FOR_ACTION)
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting reminder ID {reminder_id_to_delete} via button: {e}", exc_info=True)
                await query.edit_message_text(text=MSG_GENERAL_ERROR)
            finally:
                db.close()
                log_memory_usage(f"after DB delete via button for {user_id}")
                gc.collect()
            
            if deleted_successfully:
                # Show a temporary success message
                success_message = MSG_REMINDER_DELETED.format(task=deleted_task_desc)
                
                # Check if there are still active reminders
                db = next(get_db())
                try:
                    remaining_reminders = db.query(Reminder).filter(
                        Reminder.user_id == user_id,
                        Reminder.is_active == True
                    ).count()
                    
                    if remaining_reminders > 0:
                        # Update the message with the modified list
                        return await display_list_and_ask_delete(update, context)
                    else:
                        # If no reminders left, just show the deletion confirmation
                        await query.edit_message_text(text=success_message)
                except Exception as e:
                    logger.error(f"Error checking remaining reminders: {e}", exc_info=True)
                    await query.edit_message_text(text=success_message)
                finally:
                    db.close()
                    
            return ConversationHandler.END # End conversation or action
        except (IndexError, ValueError):
            logger.error(f"Invalid callback data for delete: {data}")
            await query.edit_message_text("خطای داخلی در پردازش درخواست حذف.")
            return ConversationHandler.END
    
    # Fallback for unhandled callback data
    logger.warning(f"Unhandled callback_data: {data} from user {user_id}")
    return ConversationHandler.END

async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    db = next(get_db())
    try:
        now_utc = datetime.datetime.now(pytz.utc)
        due_reminders = db.query(Reminder).filter(
            Reminder.due_datetime_utc <= now_utc,
            Reminder.is_active == True,
            Reminder.is_sent == False
        ).order_by(Reminder.due_datetime_utc).limit(10).all() # Limit reminders fetched per cycle

        if due_reminders: 
            logger.info(f"Scheduler: Found {len(due_reminders)} due reminders.")
            log_memory_usage("scheduler check_reminders start")

        for reminder in due_reminders:
            try:
                await context.bot.send_message(chat_id=reminder.chat_id, text=MSG_REMINDER_NOTIFICATION.format(task=reminder.task_description))
                logger.info(f"Scheduler: Sent reminder ID {reminder.id} for task '{reminder.task_description}' to user {reminder.user_id}")
                
                # Store context for potential snooze
                if reminder.user_id not in context.bot_data:
                    context.bot_data[reminder.user_id] = {}
                context.bot_data[reminder.user_id]['last_notified_reminder_id'] = reminder.id
                context.bot_data[reminder.user_id]['last_notified_task'] = reminder.task_description
                context.bot_data[reminder.user_id]['last_notified_at_utc'] = datetime.datetime.now(pytz.utc)
                
                if reminder.recurrence_rule:
                    logger.info(f"Reminder ID {reminder.id} is recurring: {reminder.recurrence_rule}")
                    next_due_time = None
                    # Basic recurrence handling (daily, weekly, monthly)
                    if reminder.recurrence_rule.lower() == "daily":
                        next_due_time = reminder.due_datetime_utc + datetime.timedelta(days=1)
                    elif reminder.recurrence_rule.lower() == "weekly":
                        next_due_time = reminder.due_datetime_utc + datetime.timedelta(weeks=1)
                    elif reminder.recurrence_rule.lower() == "monthly":
                        next_month = reminder.due_datetime_utc.month + 1
                        next_year = reminder.due_datetime_utc.year
                        if next_month > 12:
                            next_month = 1
                            next_year += 1
                        try:
                            next_due_time = reminder.due_datetime_utc.replace(year=next_year, month=next_month)
                        except ValueError: # Handle cases like Feb 29 for non-leap years
                            # Go to the last day of the target month
                            import calendar
                            last_day = calendar.monthrange(next_year, next_month)[1]
                            next_due_time = reminder.due_datetime_utc.replace(year=next_year, month=next_month, day=last_day)
                    
                    if next_due_time:
                        reminder.due_datetime_utc = next_due_time
                        reminder.is_sent = False # Ready for next send
                        logger.info(f"Rescheduled recurring reminder ID {reminder.id} to {reminder.due_datetime_utc}")
                    else:
                        logger.warning(f"Unhandled recurrence '{reminder.recurrence_rule}' for ID {reminder.id}. Deactivating.")
                        reminder.is_active = False
                        reminder.is_sent = True
                else: # Not recurring
                    reminder.is_active = False
                    reminder.is_sent = True
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Scheduler: Failed to send/process reminder ID {reminder.id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Scheduler: Error in check_reminders job: {e}", exc_info=True)
    finally:
        db.close()
        log_memory_usage("scheduler check_reminders end")
        # gc.collect() # Removed from here, will be handled by memory monitor or less frequently

# +++ SNOOZE HANDLER +++
async def handle_snooze_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handles user requests to snooze a recently sent reminder. Returns True if handled, False otherwise."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    log_memory_usage(f"snooze_request check from {user_id}: '{text}'")

    snooze_context = context.bot_data.get(user_id, {})
    last_notified_reminder_id = snooze_context.get('last_notified_reminder_id')
    last_notified_at_utc = snooze_context.get('last_notified_at_utc')

    if not last_notified_reminder_id or not last_notified_at_utc:
        # Not a snooze situation, or context is missing. Let other handlers process.
        return False

    # Check if the notification was recent (e.g., within 5 minutes)
    if (datetime.datetime.now(pytz.utc) - last_notified_at_utc) > datetime.timedelta(minutes=5):
        logger.info(f"Snooze attempt for user {user_id} is for an old notification. Clearing context.")
        context.bot_data.pop(user_id, None) # Clear stale context
        return False # Too old, not a snooze for the last notification

    # Try to parse for snooze intent / relative time
    # A simple keyword check first, NLU can be heavy
    snooze_keywords = ["دوباره یادآوری کن", "یادم بنداز باز", "ساعت دیگه", "دقیقه دیگه", "بعدا"] # Add more Persian keywords
    is_potential_snooze = any(keyword in text for keyword in snooze_keywords)

    if not is_potential_snooze:
        # If no obvious snooze keyword, it might be a regular message.
        # However, if user says "فردا ساعت ۳" right after a notification, it IS a snooze.
        # NLU is better for this.
        pass # Fall through to NLU

    logger.info(f"Potential snooze from {user_id} for reminder {last_notified_reminder_id}. Text: '{text}'")
    nlu_data = extract_reminder_details_gemini(text, current_context="snooze_request")
    log_memory_usage(f"after NLU for snooze_request from {user_id}")

    if nlu_data and (nlu_data.get("date") or nlu_data.get("time")): # NLU must provide some date/time info
        new_date_str = nlu_data.get("date")
        new_time_str = nlu_data.get("time")

        # If only time is given, assume today's date for snooze.
        # If NLU gives "date: امروز" or similar, parse_persian_datetime_to_utc handles it.
        # If NLU gives only time like "ساعت ۳", we need to ensure date is today.
        if not new_date_str and new_time_str: # e.g. "۳۰ دقیقه دیگه", "ساعت ۳"
            # parse_persian_datetime_to_utc can often handle relative times like "۳۰ دقیقه دیگه" correctly.
            # If NLU returns an absolute time like "15:00" without a date, assume today.
             pass # parse_persian_datetime_to_utc should handle relative time or use current day

        new_due_datetime_utc = parse_persian_datetime_to_utc(new_date_str, new_time_str)

        if not new_due_datetime_utc:
            await update.message.reply_text(MSG_SNOOZE_FAILURE_NLU)
            # Don't clear context yet, user might try again immediately
            return True # Stop processing this update further
        
        if new_due_datetime_utc < datetime.datetime.now(pytz.utc):
            await update.message.reply_text(MSG_REMINDER_IN_PAST.format(date=format_jalali_datetime_for_display(new_due_datetime_utc)[0], time=format_jalali_datetime_for_display(new_due_datetime_utc)[1]))
            return True

        db = next(get_db())
        try:
            reminder_to_snooze = db.query(Reminder).filter(Reminder.id == last_notified_reminder_id, Reminder.user_id == user_id).first()
            if reminder_to_snooze:
                reminder_to_snooze.due_datetime_utc = new_due_datetime_utc
                reminder_to_snooze.is_sent = False
                reminder_to_snooze.is_active = True # Ensure it's active
                db.commit()
                
                jalali_date_display, time_display_parsed = format_jalali_datetime_for_display(new_due_datetime_utc)
                await update.message.reply_text(MSG_SNOOZE_CONFIRMATION.format(task=reminder_to_snooze.task_description, time=f"{jalali_date_display} ساعت {time_display_parsed}"))
                logger.info(f"User {user_id} snoozed reminder ID {last_notified_reminder_id} to {new_due_datetime_utc}")
                context.bot_data.pop(user_id, None) # Clear context after successful snooze
            else:
                await update.message.reply_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
                context.bot_data.pop(user_id, None) # Clear context as reminder is gone
        except Exception as e:
            db.rollback()
            logger.error(f"Error snoozing reminder ID {last_notified_reminder_id}: {e}", exc_info=True)
            await update.message.reply_text(MSG_GENERAL_ERROR)
        finally:
            db.close()
            log_memory_usage(f"after DB snooze for {user_id}")
            gc.collect()
        return True # Stop processing this update further
        
    elif nlu_data and nlu_data.get("intent") == "cancel": # User says "لغو" to snooze prompt (if we had one)
        context.bot_data.pop(user_id, None)
        await update.message.reply_text(MSG_CANCELLED) # Or a more specific "snooze cancelled"
        return True

    else:
        # This means NLU didn't get a date/time for snooze from the message.
        # It could be a regular message. If we are sure user is in "snooze mode" (e.g. very recent notification),
        # we could ask "برای چه زمانی؟" - MSG_SNOOZE_ASK_TIME.
        # For now, if text is not obviously a snooze time, let it pass to other handlers.
        # However, if keywords were matched, maybe we should be more insistent.
        # The current logic: if context exists, we try NLU. If NLU fails to give time, we assume it's not a valid snooze time.
        # A better check would be if NLU intent IS "snooze_reminder" but time is missing.
        # Let's send a failure message if snooze context was present but NLU failed.
        if is_potential_snooze: # If keywords indicated snooze but NLU failed
             await update.message.reply_text(MSG_SNOOZE_FAILURE_NLU)
             return True
        # Otherwise, it's likely not a snooze message, let it go to other handlers.
        return False # Allow other handlers

def main() -> None:
    """Start the bot with memory optimization and full conversation logic."""
    log_memory_usage("bot startup")
    try:
        init_db()
        logger.info("Database initialized.")
        log_memory_usage("after DB init")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN not found! Exiting.")
        return
    
    # Ensure Google credentials are set for STT/NLU
    google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not google_creds_path or not os.path.exists(google_creds_path):
        logger.critical(f"GOOGLE_APPLICATION_CREDENTIALS file not found at path: {google_creds_path}. STT/NLU will likely fail.")
        # We can let the bot run, but STT/NLU will not work.

    gc.collect()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    persian_cancel_regex = r'^(لغو|کنسل|بیخیال|نه ممنون)$'.strip()

    # Add a wrapper for the snooze handler that only passes to the main conversation if snooze isn't handled
    async def snooze_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        handled = await handle_snooze_request(update, context)
        if not handled:
            # If snooze handler didn't handle this message, pass it to the main conversation handler
            await handle_initial_message(update, context)

    # Main Conversation Handler for setting reminders (text and voice)
    set_reminder_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(persian_cancel_regex) & ~filters.Regex(r'^یادآورهای من$') & ~filters.Regex(r'^راهنما$'), snooze_wrapper),
            MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
        ],
        states={
            AWAITING_TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_description)],
            AWAITING_FULL_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_full_datetime)],
            AWAITING_TIME_ONLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_time_only)],
            AWAITING_AM_PM_CLARIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_am_pm_clarification)],
            # Edit states are part of a separate flow triggered by CallbackQueryHandler
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.Regex(persian_cancel_regex), cancel_conversation)
        ],
        conversation_timeout=300, # 5 minutes
        name="set_reminder_conversation",
        persistent=False # To avoid issues with user_data across restarts/updates for now
    )

    # Conversation Handler for listing, deleting, and editing reminders
    # This is mainly for the edit flow that starts from a callback query
    manage_reminders_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback, pattern=r'^edit_.*|delete_.*') # Handles edit_REMINDERID and delete_REMINDERID
        ],
        states={
            AWAITING_EDIT_FIELD_CHOICE: [
                CallbackQueryHandler(button_callback, pattern=r'^edit_field_task_.*|edit_field_time_.*')
            ],
            AWAITING_EDIT_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_field_value)
            ],
            # AWAITING_DELETE_NUMBER_INPUT is not used if relying on buttons
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.Regex(persian_cancel_regex), cancel_conversation)
        ],
        conversation_timeout=180, # 3 minutes for edit interaction
        name="manage_reminders_conversation",
        persistent=False
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_reminders_entry))
    application.add_handler(MessageHandler(filters.Regex(r'^یادآورهای من$'), list_reminders_entry)) # Handle button
    application.add_handler(MessageHandler(filters.Regex(r'^راهنما$'), help_command)) # Handle button

    application.add_handler(set_reminder_conv)
    application.add_handler(manage_reminders_conv)
    # Add a standalone voice handler for non-conversational voice inputs if needed, or ensure it enters set_reminder_conv
    # For now, handle_voice_message is an entry point to set_reminder_conv

    # Fallback cancel command if user is stuck somehow
    application.add_handler(CommandHandler("cancel", cancel_conversation))
    application.add_handler(MessageHandler(filters.Regex(persian_cancel_regex), cancel_conversation))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_reminders, interval=30, first=10)
        logger.info("Reminder checking job scheduled.")

    log_memory_usage("before starting polling")
    logger.info("Starting bot with full conversational logic...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available. Memory monitoring will be disabled.")
        logger.warning("Install with: pip install psutil")
    main()