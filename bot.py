import logging
import os
import tempfile
import datetime
import pytz
import re
import asyncio
import json
from typing import Dict, Any, Tuple, Optional, List, Union

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

# Set up enhanced logging
import logging.handlers
import sys

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure the root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s",
    handlers=[
        # Console handler with INFO level
        logging.StreamHandler(sys.stdout),
        # File handler with DEBUG level (more detailed)
        logging.handlers.RotatingFileHandler(
            'logs/bot.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        ),
    ]
)

# Set the file handler to DEBUG level for detailed logging
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.handlers.RotatingFileHandler):
        handler.setLevel(logging.DEBUG)

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
    
    # Past check for non-recurring. For recurring, the first calculated date could be in the past relative to creation.
    # This logic is complex for recurrence, so for now, we only strictly check past for non-recurring.
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
        # reminder.is_active = True # Ensure it's active on save/update
        reminder.is_sent = False # Reset is_sent status on update or new

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

# --- Conversation Handler States & Functions ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["یادآورهای من", "راهنما"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(MSG_WELCOME, reply_markup=reply_markup)
    return ConversationHandler.END

async def handle_initial_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text.strip()
    context.user_data.clear() 
    logger.info(f"User {user_id} initial message: '{text}'")

    # Check for list reminders button press
    if text == "یادآورهای من":
        return await display_list_and_ask_delete(update, context)

    # Check for help button press
    if text == "راهنما":
        await update.message.reply_text(MSG_HELP)
        return ConversationHandler.END

    # Check for edit reminder request
    if re.search(r'ویرایش|تغییر', text) and re.search(r'شماره[‌\s]+\d+', text):
        return await handle_edit_reminder_request(update, context)

    # Check for multi-stage reminders
    if " و " in text and await handle_multi_stage_reminders(text, update, context):
        return ConversationHandler.END
    
    # Regular reminder processing continues below
    nlu_data = extract_reminder_details_gemini(text, current_context="initial_contact")
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
    
    if intent == "list_reminders":
        return await display_list_and_ask_delete(update, context)

    if intent == "set_reminder":
        # Scenario 1 start: Only task given -> "یادم بنداز به برادرم زنگ بزنم"
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
                context.user_data['last_reminder_id_for_time_update'] = reminder.id # For Scenario 1 & 2 continuation
                await update.message.reply_text(MSG_CONFIRM_DEFAULT_TIME.format(task=reminder.task_description, date=jalali_date))
                return AWAITING_TIME_ONLY
        
        # Scenario 3 & 4: All parts present (task, date, time)
        elif context.user_data['task'] and context.user_data['date_str'] and context.user_data['time_str']:
            # Check for AM/PM ambiguity if NLU indicated it
            if nlu_data.get("raw_time_input") and not context.user_data['am_pm']: # NLU thinks AM/PM is needed
                 ambiguous_hour_match = re.match(r"(\d{1,2})", context.user_data['time_str']) # Extract hour from HH:MM
                 if ambiguous_hour_match:
                    ambiguous_hour = int(ambiguous_hour_match.group(1))
                    logger.info(f"Time {context.user_data['time_str']} from NLU is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
                    context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour) # Store hour for prompt
                    await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=context.user_data['ambiguous_time_hour_str']))
                    return AWAITING_AM_PM_CLARIFICATION
            
            # If not ambiguous or AM/PM already resolved by NLU
            reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
            if error:
                await update.message.reply_text(error)
                return ConversationHandler.END
            if reminder:
                jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
                await update.message.reply_text(MSG_CONFIRMATION.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
                return ConversationHandler.END
        else: # Not enough parts for set_reminder (e.g., only date given initially)
            logger.info(f"Intent: set_reminder, but not enough initial parts. Task: {context.user_data['task']}, Date: {context.user_data['date_str']}. Asking for task if missing, else datetime.")
            if not context.user_data['task']:
                await update.message.reply_text(MSG_REQUEST_TASK)
                return AWAITING_TASK_DESCRIPTION
            else: # Task is there, but date/time might be partially there or missing
                 await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
                 return AWAITING_FULL_DATETIME
    else: # Other intents or unclear
        logger.info(f"NLU intent '{intent}' not directly handled as entry or is unclear. Defaulting to failure message.")
        await update.message.reply_text(MSG_FAILURE_EXTRACTION)
        return ConversationHandler.END

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_task_description")
    
    if nlu_data and nlu_data.get("intent") == "provide_task" and nlu_data.get("task"):
        context.user_data['task'] = nlu_data.get("task")
        logger.info(f"User {update.effective_user.id} provided task: {context.user_data['task']}. Asking for datetime.")
        await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
        return AWAITING_FULL_DATETIME
    elif nlu_data and nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)
    else: # If user types something else or NLU fails
        await update.message.reply_text(MSG_REQUEST_TASK + " (لطفاً موضوع یادآور را بنویسید یا 'لغو' کنید)")
        return AWAITING_TASK_DESCRIPTION

async def received_full_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    logger.info(f"User {user_id} (state AWAITING_FULL_DATETIME) provided: '{text}' for task '{context.user_data.get('task')}'")

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_full_datetime")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return AWAITING_FULL_DATETIME # Stay in state

    if nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)

    date_str = nlu_data.get("date")
    time_str = nlu_data.get("time")
    # Update context with potentially new recurrence from this input
    if nlu_data.get("recurrence"): context.user_data['recurrence'] = nlu_data.get("recurrence")
    if nlu_data.get("am_pm"): context.user_data['am_pm'] = nlu_data.get("am_pm")


    if not date_str:
        await update.message.reply_text(MSG_DATE_PARSE_ERROR + "\n" + MSG_REQUEST_FULL_DATETIME)
        return AWAITING_FULL_DATETIME

    context.user_data['date_str'] = date_str
    
    if not time_str: # Date provided, time is missing (default to 9 AM) - Scenario 1 continuation
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
    else: # Both date and time seem to be provided
        context.user_data['time_str'] = time_str
        if nlu_data.get("raw_time_input") and not nlu_data.get("am_pm"): # NLU thinks AM/PM is needed
            ambiguous_hour_match = re.match(r"(\d{1,2})", time_str)
            if ambiguous_hour_match:
                ambiguous_hour = int(ambiguous_hour_match.group(1))
                logger.info(f"Time {time_str} from NLU is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
                context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
                await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=str(ambiguous_hour)))
                return AWAITING_AM_PM_CLARIFICATION
        
        # If not ambiguous or AM/PM was resolved by NLU
        reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
        if error:
            await update.message.reply_text(error)
            return ConversationHandler.END # Or back to AWAITING_FULL_DATETIME if parse error
        if reminder:
            jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
            rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
            await update.message.reply_text(MSG_CONFIRMATION.format(task=context.user_data['task'], date=jalali_date, time=time_disp, recurrence_info=rec_info))
            return ConversationHandler.END

async def received_time_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This state is entered after a reminder was set for 09:00 AM by default,
    # and bot asked "اگر ساعت دیگری مد نظر داری، لطفاً فقط ساعت را اعلام کن"
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    logger.info(f"User {user_id} (state AWAITING_TIME_ONLY) provided: '{text}' to change time for reminder ID {context.user_data.get('last_reminder_id_for_time_update')}")

    reminder_id_to_update = context.user_data.get('last_reminder_id_for_time_update')
    if not reminder_id_to_update or not context.user_data.get('task') or not context.user_data.get('date_str'):
        await update.message.reply_text(MSG_GENERAL_ERROR + " (اطلاعات یادآور قبلی برای تغییر ساعت یافت نشد. لطفاً از ابتدا شروع کنید.)")
        return ConversationHandler.END

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_time_only")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return AWAITING_TIME_ONLY

    if nlu_data.get("intent") == "cancel":
        await update.message.reply_text(MSG_CANCELLED + " (یادآور قبلی در ساعت ۹ صبح باقی ماند).")
        return ConversationHandler.END
    if nlu_data.get("intent") == "negative": # User said "نه" or similar to changing time
        await update.message.reply_text("بسیار خب، یادآور در همان ساعت ۹ صبح باقی ماند.")
        return ConversationHandler.END


    if nlu_data.get("intent") not in ["provide_time", "set_reminder"] or not nlu_data.get("time"):
        await update.message.reply_text(MSG_DATE_PARSE_ERROR + " (فرمت ساعت نامفهوم است).\n" + MSG_REQUEST_TIME_ONLY)
        return AWAITING_TIME_ONLY

    new_time_str = nlu_data.get("time")
    context.user_data['time_str'] = new_time_str # This is the new time
    if nlu_data.get("am_pm"): context.user_data['am_pm'] = nlu_data.get("am_pm")


    if nlu_data.get("raw_time_input") and not nlu_data.get("am_pm"):
        ambiguous_hour_match = re.match(r"(\d{1,2})", new_time_str)
        if ambiguous_hour_match:
            ambiguous_hour = int(ambiguous_hour_match.group(1))
            logger.info(f"New time '{new_time_str}' is ambiguous. Asking AM/PM for hour {ambiguous_hour}.")
            context.user_data['ambiguous_time_hour_str'] = str(ambiguous_hour)
            await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=str(ambiguous_hour)))
            return AWAITING_AM_PM_CLARIFICATION # This state will handle update upon AM/PM receipt

    # If time is not ambiguous, update the reminder
    reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data, reminder_id_to_update)
    if error:
        await update.message.reply_text(error)
        # Decide if we should end or stay. If parse error, maybe stay.
        if error == MSG_DATE_PARSE_ERROR:
            return AWAITING_TIME_ONLY
        return ConversationHandler.END
    if reminder:
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
        rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
        await update.message.reply_text(MSG_CONFIRMATION_UPDATE.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
    return ConversationHandler.END

async def received_am_pm_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    logger.info(f"User {user_id} (state AWAITING_AM_PM_CLARIFICATION) provided AM/PM: '{text}' for hour {context.user_data.get('ambiguous_time_hour_str')}")

    ambiguous_hour_str = context.user_data.get('ambiguous_time_hour_str')
    if not ambiguous_hour_str: # Should not happen if state logic is correct
        await update.message.reply_text(MSG_GENERAL_ERROR + " (زمینه ساعت برای تعیین صبح/عصر یافت نشد)")
        return ConversationHandler.END

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_am_pm_clarification")
    if not nlu_data:
        await update.message.reply_text(MSG_NLU_ERROR)
        return AWAITING_AM_PM_CLARIFICATION # Stay

    if nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)
        
    if nlu_data.get("intent") != "provide_am_pm" or not nlu_data.get("am_pm"):
        await update.message.reply_text(MSG_ASK_AM_PM.format(time_hour=ambiguous_hour_str) + " (لطفاً فقط 'صبح'، 'ظهر' یا 'بعد از ظهر' را مشخص کنید)")
        return AWAITING_AM_PM_CLARIFICATION

    am_pm_specifier = nlu_data.get("am_pm") # "am" or "pm"
    hour_12_format = int(ambiguous_hour_str)
    
    hour_24_format = hour_12_format
    if am_pm_specifier == "pm" and hour_12_format < 12: # e.g. 1 PM -> 13
        hour_24_format += 12
    elif am_pm_specifier == "am" and hour_12_format == 12: # 12 AM (midnight) -> 00
        hour_24_format = 0
    # Note: 12 PM (noon) is 12 in 24h. 12 AM (midnight) is 00.
    # NLU prompt maps "ظهر" to "pm", so 12 + "pm" (ظهر) should be 12.
    
    # Assuming the minute part was '00' for the ambiguous hour, or get it from previous NLU time.
    minute_str = "00"
    # If 'time_str' (HH:MM) was already partially set from ambiguous NLU output (e.g. NLU gave "12:00" for "ساعت ۱۲")
    if context.user_data.get('time_str') and ':' in context.user_data['time_str']:
        minute_str = context.user_data['time_str'].split(':')[1]
    
    context.user_data['time_str'] = f"{hour_24_format:02d}:{minute_str}"
    context.user_data['am_pm'] = am_pm_specifier # Store resolved am_pm

    # Now, decide if we were clarifying for an initial reminder or an update
    reminder_id_to_update = context.user_data.get('last_reminder_id_for_time_update')
    reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data, reminder_id_to_update)

    if error:
        await update.message.reply_text(error)
        return ConversationHandler.END 
    if reminder:
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
        rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
        if reminder_id_to_update:
            await update.message.reply_text(MSG_CONFIRMATION_UPDATE.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
        else:
            await update.message.reply_text(MSG_CONFIRMATION.format(task=reminder.task_description, date=jalali_date, time=time_disp, recurrence_info=rec_info))
    return ConversationHandler.END

# --- List and Delete Reminders ---
async def display_list_and_ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
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
        return ConversationHandler.END # End if list is empty

    response_text = MSG_LIST_HEADER + "\n"
    display_map = {} 
    keyboard = []
    
    for index, reminder_obj in enumerate(reminders_from_db, 1):
        jalali_date, time_disp = format_jalali_datetime_for_display(reminder_obj.due_datetime_utc)
        recurrence_info = f" (تکرار: {reminder_obj.recurrence_rule})" if reminder_obj.recurrence_rule else ""
        response_text += MSG_LIST_ITEM.format(
            index=index, 
            task=reminder_obj.task_description, 
            date=jalali_date, 
            time=time_disp,
            recurrence_info=recurrence_info
        ) + "\n"
        display_map[index] = reminder_obj.id
        
        # Add inline buttons for each reminder
        edit_button = InlineKeyboardButton(f"✏️ ویرایش #{index}", callback_data=f"edit_{reminder_obj.id}")
        delete_button = InlineKeyboardButton(f"🗑️ حذف #{index}", callback_data=f"delete_{reminder_obj.id}")
        keyboard.append([edit_button, delete_button])
    
    context.user_data['reminders_list_map'] = display_map
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(response_text, reply_markup=reply_markup)
    
    return AWAITING_DELETE_NUMBER_INPUT

async def list_reminders_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /list command"""
    return await display_list_and_ask_delete(update, context)


async def received_delete_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info(f"User {user_id} (state AWAITING_DELETE_NUMBER_INPUT) response for deletion: '{text}'")

    nlu_data = extract_reminder_details_gemini(text, current_context="awaiting_delete_number_input")
    if nlu_data and nlu_data.get("intent") == "cancel":
        return await cancel_conversation(update, context)

    selected_index = None
    if nlu_data and nlu_data.get("intent") == "delete_reminder_by_number" and nlu_data.get("extracted_number") is not None:
        selected_index = nlu_data.get("extracted_number")
    else: 
        try:
            selected_index = int(normalize_persian_numerals(text) or "-1") # Normalize if user types Persian number
        except ValueError:
            pass # Will be handled by invalid selection

    reminders_map = context.user_data.get('reminders_list_map', {})
    reminder_id_to_delete = reminders_map.get(selected_index)

    if not reminder_id_to_delete:
        await update.message.reply_text(MSG_INVALID_SELECTION + "\n" + MSG_SELECT_FOR_DELETE)
        return AWAITING_DELETE_NUMBER_INPUT # Stay in state

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
    
    context.user_data.clear()
    return ConversationHandler.END

# --- General Cancel and Timeout ---
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"User {user_id} cancelled conversation. Current state: {context.user_data.get('_conversation_state')}") # PTB might store state here
    await update.message.reply_text(MSG_CANCELLED, reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"Conversation timed out for user {user_id}. Current state: {context.user_data.get('_conversation_state')}")
    
    # Check if context.user_data has anything, sometimes timeout might occur before update is processed
    chat_id_to_reply = update.effective_chat.id if update.effective_chat else context.user_data.get('chat_id')
    
    if chat_id_to_reply:
        await context.bot.send_message(chat_id=chat_id_to_reply, text="زمان مکالمه به پایان رسید. لطفاً دوباره شروع کنید.")
    context.user_data.clear()
    return ConversationHandler.END

# --- STT Handler ---
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice: return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(f"User {user_id} sent voice message. Duration: {update.message.voice.duration}s")
    
    # Show processing message
    processing_msg = await update.message.reply_text(MSG_PROCESSING_VOICE)
    
    try:
        # Download the voice file
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as temp_audio_file:
            await voice_file.download_to_drive(custom_path=temp_audio_file.name)
            temp_audio_file_path = temp_audio_file.name
        
        logger.info(f"Voice file downloaded to {temp_audio_file_path}")
        
        # Transcribe the voice message
        transcribed_text = transcribe_voice_persian(temp_audio_file_path)
        
        # Clean up the temporary file
        try: 
            os.remove(temp_audio_file_path)
            logger.debug(f"Temp voice file {temp_audio_file_path} deleted")
        except OSError as e: 
            logger.error(f"Error deleting temp voice file {temp_audio_file_path}: {e}")

        # Remove the processing message
        if processing_msg:
            try: 
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_msg.message_id)
                logger.debug("Processing message deleted")
            except Exception as e: 
                logger.error(f"Failed to delete processing voice message: {e}")

        # Handle transcription result
        if not transcribed_text:
            logger.warning(f"Voice transcription failed for user {user_id}")
            await update.message.reply_text(MSG_STT_FAILED)
            return

        logger.info(f"Transcription for user {user_id}: \"{transcribed_text}\"")
        
        # Reply with transcription
        await update.message.reply_text(f"پیام صوتی شما: «{transcribed_text}»")
        
        # Process the transcribed text directly
        logger.info(f"Sending transcription to NLU: '{transcribed_text}'")
        
        try:
            # Add a small delay to ensure the transcription message is displayed before processing
            await asyncio.sleep(0.5)
            
            # Process the transcribed text using NLU to extract reminder details
            nlu_data = extract_reminder_details_gemini(transcribed_text, current_context="voice_transcription")
            if not nlu_data:
                logger.error(f"Failed to extract reminder details from transcription: '{transcribed_text}'")
                await update.message.reply_text(MSG_NLU_ERROR)
                return
            
            logger.info(f"NLU extracted data: {nlu_data}")
                
            # Store extracted data in user context
            context.user_data['nlu_data'] = nlu_data
            context.user_data['task'] = nlu_data.get("task")
            context.user_data['date_str'] = nlu_data.get("date")
            context.user_data['time_str'] = nlu_data.get("time")
            context.user_data['recurrence'] = nlu_data.get("recurrence")
            context.user_data['am_pm'] = nlu_data.get("am_pm")
            
            logger.info(f"Extracted task: '{context.user_data['task']}', date: '{context.user_data['date_str']}', time: '{context.user_data['time_str']}'")
            
            # If we have task and date/time, save the reminder
            if context.user_data['task'] and context.user_data['date_str'] and context.user_data['time_str']:
                logger.info(f"Creating reminder with task, date, and time")
                reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
                if error:
                    logger.error(f"Error saving reminder: {error}")
                    await update.message.reply_text(error)
                    return
                    
                if reminder:
                    jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                    rec_info = f" (تکرار: {reminder.recurrence_rule})" if reminder.recurrence_rule else ""
                    await update.message.reply_text(MSG_CONFIRMATION.format(
                        task=reminder.task_description,
                        date=jalali_date,
                        time=time_disp,
                        recurrence_info=rec_info
                    ))
                    logger.info(f"Successfully created reminder from voice message. ID: {reminder.id}")
                    
            # If we have task and date but no time, set default time and ask for confirmation
            elif context.user_data['task'] and context.user_data['date_str'] and not context.user_data['time_str']:
                logger.info(f"Voice message with task & date, but no time. Setting default 09:00.")
                context.user_data['time_str'] = "09:00"
                
                reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, context.user_data)
                if error:
                    logger.error(f"Error saving reminder with default time: {error}")
                    await update.message.reply_text(error)
                    return
                    
                if reminder:
                    jalali_date, _ = format_jalali_datetime_for_display(reminder.due_datetime_utc)
                    context.user_data['last_reminder_id_for_time_update'] = reminder.id
                    await update.message.reply_text(MSG_CONFIRM_DEFAULT_TIME.format(
                        task=reminder.task_description,
                        date=jalali_date
                    ))
                    logger.info(f"Created reminder with default time. ID: {reminder.id}")
                    
            # If we only have a task, ask for date/time
            elif context.user_data['task']:
                logger.info(f"Only task extracted from voice. Asking for date/time.")
                await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
                
            # If we couldn't extract any meaningful info
            else:
                logger.warning(f"No meaningful information extracted from transcription: '{transcribed_text}'")
                await update.message.reply_text(MSG_FAILURE_EXTRACTION)
                
        except Exception as e:
            logger.error(f"Error processing transcribed voice message: {e}", exc_info=True)
            await update.message.reply_text("متأسفانه در پردازش پیام صوتی شما مشکلی پیش آمد. لطفاً پیام خود را به صورت متنی ارسال کنید.")
    
    except Exception as e:
        logger.error(f"Global error in voice message handling: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR + " (خطای پردازش پیام صوتی)")

# --- Scheduler ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    db = next(get_db())
    try:
        now_utc = datetime.datetime.now(pytz.utc)
        due_reminders = db.query(Reminder).filter(
            Reminder.due_datetime_utc <= now_utc,
            Reminder.is_active == True,
            Reminder.is_sent == False # Only send if not already marked sent (for this instance)
        ).all()

        if due_reminders: logger.info(f"Scheduler: Found {len(due_reminders)} due reminders.")
        for reminder in due_reminders:
            try:
                await context.bot.send_message(chat_id=reminder.chat_id, text=MSG_REMINDER_NOTIFICATION.format(task=reminder.task_description))
                logger.info(f"Scheduler: Sent reminder ID {reminder.id} for task '{reminder.task_description}'")
                
                if reminder.recurrence_rule:
                    logger.info(f"Reminder ID {reminder.id} is recurring: {reminder.recurrence_rule}")
                    # More advanced recurrence handling
                    next_due_time = None
                    recurring_type = "روزانه"
                    
                    if reminder.recurrence_rule.lower() == "daily":
                        next_due_time = reminder.due_datetime_utc + datetime.timedelta(days=1)
                        recurring_type = "روزانه"
                    elif reminder.recurrence_rule.lower() == "weekly":
                        next_due_time = reminder.due_datetime_utc + datetime.timedelta(weeks=1)
                        recurring_type = "هفتگی"
                    elif reminder.recurrence_rule.lower() == "monthly":
                        # Add one month (approximately)
                        next_month = reminder.due_datetime_utc.month + 1
                        next_year = reminder.due_datetime_utc.year
                        if next_month > 12:
                            next_month = 1
                            next_year += 1
                        next_due_time = reminder.due_datetime_utc.replace(year=next_year, month=next_month)
                        recurring_type = "ماهانه"
                    elif reminder.recurrence_rule.lower().startswith("every "):
                        # Handle "every monday", "every friday", etc.
                        parts = reminder.recurrence_rule.lower().split()
                        if len(parts) >= 2 and parts[0] == "every":
                            day_name = parts[1]
                            weekday_map = {"monday": 0, "tuesday": 1, "wednesday": 2, 
                                          "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
                            if day_name in weekday_map:
                                target_weekday = weekday_map[day_name]
                                days_ahead = (target_weekday - reminder.due_datetime_utc.weekday()) % 7
                                if days_ahead == 0:
                                    days_ahead = 7  # Next week
                                next_due_time = reminder.due_datetime_utc + datetime.timedelta(days=days_ahead)
                                recurring_type = f"هر {day_name}"
                    
                    if next_due_time:
                        reminder.due_datetime_utc = next_due_time
                        reminder.is_sent = False # Ready for next send
                        logger.info(f"Rescheduled recurring reminder ID {reminder.id} to {reminder.due_datetime_utc}")
                    else: # Unhandled or non-repeating part of a rule, or rule ended.
                        logger.warning(f"Unhandled recurrence '{reminder.recurrence_rule}' or finished for ID {reminder.id}. Deactivating.")
                        reminder.is_active = False
                        reminder.is_sent = True # Mark as sent for this last instance
                else: # Not recurring
                    reminder.is_active = False # Deactivate after sending
                    reminder.is_sent = True
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Scheduler: Failed to send/process reminder ID {reminder.id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Scheduler: Error in check_reminders job: {e}", exc_info=True)
    finally:
        db.close()

# Add this after the display_list_and_ask_delete function and before list_reminders_entry
async def handle_multi_stage_reminders(text, update, context):
    """Handle reminders with multiple parts like 'Remind me to do X on Monday and Y on Tuesday'"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check for 'and' pattern or multiple dates/actions in the text
    parts = text.split(' و ')  # Split by Persian 'and'
    
    if len(parts) <= 1:
        return False  # Not a multi-stage reminder
    
    created_reminders = []
    response_parts = []
    
    for part in parts:
        # Extract details for each part
        nlu_data = extract_reminder_details_gemini(part, current_context="multi_stage_part")
        if not nlu_data or nlu_data.get("intent") != "set_reminder" or not nlu_data.get("task"):
            continue
            
        # Setup reminder data for this part
        reminder_data = {
            'task': nlu_data.get("task"),
            'date_str': nlu_data.get("date"),
            'time_str': nlu_data.get("time", "09:00"),  # Default time if not specified
            'recurrence': nlu_data.get("recurrence")
        }
        
        # Save the reminder
        reminder, error = await save_or_update_reminder_in_db(user_id, chat_id, reminder_data)
        if error:
            continue
            
        if reminder:
            jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
            created_reminders.append(reminder)
            response_parts.append(f"📝 متن: {reminder.task_description}\n⏰ زمان: {jalali_date}، ساعت {time_disp}")
    
    if created_reminders:
        # Format the response
        response = "باشه، دو یادآوری تنظیم شد:\n" + "\n\n".join(response_parts)
        await update.message.reply_text(response)
        return True
    
    return False

# Add this after the received_delete_number_input function
async def handle_edit_reminder_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle requests to edit a specific reminder"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Extract the reminder number from input like "یادآور شماره ۱ رو ویرایش کن"
    reminder_number_match = re.search(r'شماره[‌\s]+(\d+)', normalize_persian_numerals(text))
    if not reminder_number_match:
        return ConversationHandler.END
        
    reminder_index = int(reminder_number_match.group(1))
    
    # Get the user's reminders
    db = next(get_db())
    try:
        reminders_from_db = db.query(Reminder).filter(
            Reminder.user_id == user_id,
            Reminder.is_active == True
        ).order_by(Reminder.due_datetime_utc).all()
        
        if not reminders_from_db or reminder_index > len(reminders_from_db):
            await update.message.reply_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
            return ConversationHandler.END
            
        # Get the reminder to edit
        reminder_to_edit = reminders_from_db[reminder_index - 1]
        context.user_data['reminder_to_edit_id'] = reminder_to_edit.id
        context.user_data['reminder_to_edit_task'] = reminder_to_edit.task_description
        
        # Ask what field to edit
        await update.message.reply_text(MSG_EDIT_REMINDER_FIELD_CHOICE)
        return AWAITING_EDIT_FIELD_CHOICE
    except Exception as e:
        logger.error(f"Error finding reminder to edit: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR)
        return ConversationHandler.END
    finally:
        db.close()

async def received_edit_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's choice of which field to edit (time or text)"""
    text = update.message.text.strip().lower()
    
    # Check if user wants to edit time or text
    if 'زمان' in text or 'ساعت' in text or 'تاریخ' in text:
        context.user_data['edit_field'] = 'time'
        await update.message.reply_text(MSG_REQUEST_FULL_DATETIME)
        return AWAITING_EDIT_FIELD_VALUE
    elif 'متن' in text or 'موضوع' in text:
        context.user_data['edit_field'] = 'text'
        await update.message.reply_text(MSG_REQUEST_TASK)
        return AWAITING_EDIT_FIELD_VALUE
    else:
        await update.message.reply_text("لطفاً مشخص کنید می‌خواهید متن را تغییر دهید یا زمان را.")
        return AWAITING_EDIT_FIELD_CHOICE

async def received_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the new value for the edited field"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    reminder_id = context.user_data.get('reminder_to_edit_id')
    edit_field = context.user_data.get('edit_field')
    
    if not reminder_id or not edit_field:
        await update.message.reply_text(MSG_GENERAL_ERROR)
        return ConversationHandler.END
    
    db = next(get_db())
    try:
        reminder = db.query(Reminder).filter(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.is_active == True
        ).first()
        
        if not reminder:
            await update.message.reply_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
            return ConversationHandler.END
        
        if edit_field == 'text':
            # Update the reminder text
            reminder.task_description = text
            db.commit()
            
            jalali_date, time_disp = format_jalali_datetime_for_display(reminder.due_datetime_utc)
            await update.message.reply_text(
                MSG_EDIT_REMINDER_UPDATED.format(
                    task=reminder.task_description,
                    date=jalali_date,
                    time=time_disp
                )
            )
            return ConversationHandler.END
            
        elif edit_field == 'time':
            # Extract new date/time from text
            nlu_data = extract_reminder_details_gemini(text, current_context="editing_reminder_time")
            
            if not nlu_data:
                await update.message.reply_text(MSG_NLU_ERROR)
                return AWAITING_EDIT_FIELD_VALUE
                
            date_str = nlu_data.get("date")
            time_str = nlu_data.get("time")
            
            if not date_str or not time_str:
                await update.message.reply_text(MSG_DATE_PARSE_ERROR)
                return AWAITING_EDIT_FIELD_VALUE
                
            # Parse the new date/time
            new_due_datetime = parse_persian_datetime_to_utc(date_str, time_str)
            if not new_due_datetime:
                await update.message.reply_text(MSG_DATE_PARSE_ERROR)
                return AWAITING_EDIT_FIELD_VALUE
                
            # Update the reminder time
            reminder.due_datetime_utc = new_due_datetime
            db.commit()
            
            jalali_date, time_disp = format_jalali_datetime_for_display(new_due_datetime)
            await update.message.reply_text(
                MSG_EDIT_REMINDER_UPDATED.format(
                    task=reminder.task_description,
                    date=jalali_date,
                    time=time_disp
                )
            )
            return ConversationHandler.END
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating reminder: {e}", exc_info=True)
        await update.message.reply_text(MSG_GENERAL_ERROR)
        return ConversationHandler.END
    finally:
        db.close()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("edit_"):
        reminder_id = int(data.split("_")[1])
        context.user_data['reminder_to_edit_id'] = reminder_id
        
        # Get reminder details
        db = next(get_db())
        try:
            reminder = db.query(Reminder).filter(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
                Reminder.is_active == True
            ).first()
            
            if not reminder:
                await query.edit_message_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
                return ConversationHandler.END
                
            context.user_data['reminder_to_edit_task'] = reminder.task_description
            
            # Ask what to edit with inline buttons
            keyboard = [
                [
                    InlineKeyboardButton("📝 متن", callback_data="edit_field_text"),
                    InlineKeyboardButton("🕒 زمان", callback_data="edit_field_time")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                MSG_EDIT_REMINDER_FIELD_CHOICE,
                reply_markup=reply_markup
            )
            return AWAITING_EDIT_FIELD_CHOICE
            
        except Exception as e:
            logger.error(f"Error finding reminder to edit: {e}", exc_info=True)
            await query.edit_message_text(MSG_GENERAL_ERROR)
            return ConversationHandler.END
        finally:
            db.close()
            
    elif data.startswith("delete_"):
        reminder_id = int(data.split("_")[1])
        
        db = next(get_db())
        try:
            reminder = db.query(Reminder).filter(
                Reminder.id == reminder_id, 
                Reminder.user_id == user_id, 
                Reminder.is_active == True
            ).first()
            
            if reminder:
                reminder.is_active = False  # Soft delete
                db.commit()
                await query.edit_message_text(
                    MSG_REMINDER_DELETED.format(task=reminder.task_description)
                )
            else:
                await query.edit_message_text(MSG_REMINDER_NOT_FOUND_FOR_ACTION)
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting reminder ID {reminder_id}: {e}", exc_info=True)
            await query.edit_message_text(MSG_GENERAL_ERROR)
        finally:
            db.close()
            
        return ConversationHandler.END
        
    elif data.startswith("edit_field_"):
        field = data.split("_")[2]
        context.user_data['edit_field'] = field
        
        if field == "text":
            await query.edit_message_text(MSG_REQUEST_TASK)
            return AWAITING_EDIT_FIELD_VALUE
        elif field == "time":
            await query.edit_message_text(MSG_REQUEST_FULL_DATETIME)
            return AWAITING_EDIT_FIELD_VALUE
            
    return ConversationHandler.END

def main() -> None:
    init_db()
    logger.info("Database initialized.")

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN not found! Exiting.")
        return
    google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not google_creds_path or not os.path.exists(google_creds_path):
        logger.critical(f"GOOGLE_APPLICATION_CREDENTIALS file not found at path: {google_creds_path}. STT/NLU will fail. Exiting.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Regex for "cancel" in Persian
    persian_cancel_regex = r'^(لغو|کنسل|بیخیال|نه ممنون)$' # Added "نه ممنون"

    # Main Conversation Handler for setting reminders
    set_reminder_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_initial_message),
            MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
        ],
        states={
            AWAITING_TASK_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_description),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_FULL_DATETIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_full_datetime),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_TIME_ONLY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_time_only),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_AM_PM_CLARIFICATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_am_pm_clarification),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_EDIT_FIELD_CHOICE: [
                CallbackQueryHandler(button_callback, pattern=r'^edit_field_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_field_choice),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_EDIT_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_field_value),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.Regex(persian_cancel_regex), cancel_conversation)
        ],
        # Setting a conversation timeout so the user is not stuck if they abandon the interaction
        conversation_timeout=300, # 5 minutes in seconds
        name="set_reminder_conversation"
    )
    
    # Conversation Handler for listing and then deleting reminders
    list_delete_conv = ConversationHandler(
        entry_points=[
            CommandHandler("list", list_reminders_entry),
            MessageHandler(filters.Regex(r'^یادآورهای من$'), display_list_and_ask_delete)
        ],
        states={
            AWAITING_DELETE_NUMBER_INPUT: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_delete_number_input),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_EDIT_FIELD_CHOICE: [
                CallbackQueryHandler(button_callback, pattern=r'^edit_field_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_field_choice),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
            AWAITING_EDIT_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit_field_value),
                MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_message)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            MessageHandler(filters.Regex(persian_cancel_regex), cancel_conversation)
        ],
        conversation_timeout=120 # 2 minutes for this interaction
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(set_reminder_conv)
    application.add_handler(list_delete_conv)
    
    # Fallback cancel command if user is stuck somehow (not in a conversation)
    application.add_handler(CommandHandler("cancel", cancel_conversation))


    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_reminders, interval=30, first=5) # Check every 30s
        logger.info("Reminder checking job scheduled.")

    logger.info("Bot starting to poll...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()