import logging
import os
import tempfile
import datetime
import pytz
import re
import gc  # Garbage collection for memory management
import math # For math.ceil in pagination
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union, Callable

# Import only what we need from telegram to reduce memory usage
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from sqlalchemy.orm import Session

# Assuming config.py defines necessary constants like MSG_HELP, etc.
# and settings are imported from config.config
from config.config import settings # For settings like API keys, PAYMENT_AMOUNT
from config.config import MSG_ERROR_GENERIC, MSG_WELCOME, MSG_PRIVACY_POLICY # Import all needed messages
# It's recommended to move message constants to a dedicated config/messages.py or include them in config.config.py

from .database import init_db, get_db
from .models import Reminder, User
from .payment import create_payment_link, verify_payment, is_user_premium, PaymentStatus, ZibalPaymentError

# Import the LangGraph app
from .graph import lang_graph_app
from .graph_state import AgentState # For type hinting initial state

# Simple logging with file backup but minimal memory usage
log_path = Path(settings.LOG_FILE_PATH)
if not log_path.parent.exists():
    os.makedirs(log_path.parent, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=settings.LOG_LEVEL, # Use log level from settings
    handlers=[
        logging.FileHandler(filename=settings.LOG_FILE_PATH, mode='a', encoding='utf-8'),
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
    AWAITING_PRIMARY_EVENT_TIME
) = range(8)

# Memory monitoring function
def log_memory_usage(context_info: str = ""):
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024
        logger.info(f"Memory usage {context_info}: {mem_mb:.2f}MB (RSS)")
        if mem_mb > 1800:
            logger.warning(f"High memory usage detected ({mem_mb:.2f}MB). Running garbage collection...")
            gc.collect()
    except ImportError:
        logger.debug("psutil not installed - can't monitor memory usage for dev environment.")
    except Exception as e:
        logger.error(f"Error monitoring memory: {e}")

async def _handle_graph_invocation(
    update_obj: Union[Update, None],
    context: ContextTypes.DEFAULT_TYPE,
    initial_state: AgentState,
    is_callback: bool = False,
    is_start_command: bool = False # Added flag for start command
) -> None:
    """Helper function to invoke LangGraph and handle its response."""
    if not update_obj or not update_obj.effective_user:
        logger.warning("_handle_graph_invocation called with invalid update_obj or missing effective_user")
        return

    user_id = update_obj.effective_user.id
    config = {"configurable": {"thread_id": f"user_{user_id}"}}
    response_target = update_obj.message if update_obj.message else (update_obj.callback_query.message if update_obj.callback_query else None)
    if not response_target:
        logger.error(f"Could not determine response target for user {user_id}")
        return

    try:
        logger.debug(f"Invoking LangGraph for user {user_id}, input: '{initial_state.get('input_text')}', type: '{initial_state.get('message_type')}'")
        final_state_result = await lang_graph_app.ainvoke(initial_state, config=config)

        response_text = final_state_result.get("response_text")
        response_keyboard_markup_dict = final_state_result.get("response_keyboard_markup")
        action_to_take = final_state_result.get("message_action") # e.g., "edit", "send_new", "delete"
        target_message_id = final_state_result.get("target_message_id", response_target.message_id if response_target else None)

        if final_state_result.get("error_message"):
            logger.error(f"Error from LangGraph for user {user_id}: {final_state_result.get('error_message')}")
            await response_target.reply_text(MSG_ERROR_GENERIC)
            return
        
        reply_markup = None
        # Define the persistent reply keyboard
        persistent_reply_keyboard = ReplyKeyboardMarkup(
            [["یادآورهای من", "یادآور نامحدود 👑"]],
            resize_keyboard=True
        )

        if response_keyboard_markup_dict: # If graph wants to send a specific InlineKeyboard
            if response_keyboard_markup_dict.get("type") == "InlineKeyboardMarkup":
                buttons = []
                for row_data in response_keyboard_markup_dict.get("inline_keyboard", []):
                    button_row = []
                    for btn_data in row_data:
                        if btn_data.get("web_app"):
                            button_row.append(InlineKeyboardButton(text=btn_data.get("text"), web_app=WebAppInfo(url=btn_data.get("web_app").get("url"))))
                        else:
                            button_row.append(InlineKeyboardButton(text=btn_data.get("text"), callback_data=btn_data.get("callback_data"), url=btn_data.get("url")))
                    buttons.append(button_row)
                if buttons:
                    reply_markup = InlineKeyboardMarkup(buttons)
            # Note: We are not supporting the graph sending a custom ReplyKeyboardMarkup anymore, 
            # as we now have a persistent one. If an inline keyboard is not specified,
            # the persistent one will be used for /start, or no specific markup for other messages if not inline.
        
        if is_start_command:
            reply_markup = persistent_reply_keyboard # Always show persistent keyboard on /start

        if response_text:
            if is_callback and action_to_take == "edit" and target_message_id:
                await context.bot.edit_message_text(
                    chat_id=response_target.chat_id,
                    message_id=target_message_id,
                    text=response_text,
                    reply_markup=reply_markup # This will be an InlineKeyboardMarkup or None
                )
            elif is_callback and action_to_take == "delete" and target_message_id:
                await context.bot.delete_message(chat_id=response_target.chat_id, message_id=target_message_id)
                if response_text != "" and response_text is not None: # Send if confirmation text for deletion
                    await context.bot.send_message(chat_id=response_target.chat_id, text=response_text, reply_markup=reply_markup)
            else: # Default to sending a new message
                # If it's the start command, reply_markup is persistent_reply_keyboard.
                # If it's another command/message and graph provided an inline keyboard, reply_markup is that.
                # Otherwise, reply_markup is None, and Telegram client keeps showing the last active ReplyKeyboard (our persistent one).
                await response_target.reply_text(response_text, reply_markup=reply_markup)
        elif not response_text and is_callback and action_to_take == "delete" and target_message_id:
            # If no text but action is delete (e.g. message was deleted and no further text needed)
             await context.bot.delete_message(chat_id=response_target.chat_id, message_id=target_message_id)
        elif not response_text and is_callback:
            pass # Already answered callback
        elif not response_text and not is_callback:
            logger.warning(f"LangGraph did not return a response_text for user {user_id}, type '{initial_state.get('message_type')}'")
            await response_target.reply_text(MSG_ERROR_GENERIC)

    except Exception as e:
        logger.error(f"Error in _handle_graph_invocation for user {user_id}: {e}", exc_info=True)
        if response_target:
            await response_target.reply_text(MSG_ERROR_GENERIC)

# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("start_command received an update without message, user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    command_text = update.message.text 

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=command_text,
        message_type="command",
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        # Default empty/None for other fields to be filled by graph
        transcribed_text=None, conversation_history=[], current_intent=None,
        extracted_parameters={}, nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )
    await _handle_graph_invocation(update, context, initial_state, is_start_command=True) # Pass is_start_command=True
    log_memory_usage(f"after start_command for user {user_id}")

async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("payment_command received an update without message, user or chat.")
        return
        
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    command_text = update.message.text

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=command_text,
        message_type="command",
        current_intent="intent_payment_initiate", # Pre-set intent for /pay
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=None, conversation_history=[],
        extracted_parameters={}, nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after payment_command for user {user_id}")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("privacy_command received an update without message, user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    command_text = update.message.text

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=command_text,
        message_type="command",
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=None, conversation_history=[], current_intent=None,
        extracted_parameters={}, nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after privacy_command for user {user_id}")

async def handle_zibal_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("handle_zibal_webhook received an update without message, user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    full_command_text = update.message.text # e.g., "/zibal_webhook trackId=123&status=1&success=1"
    logger.info(f"Received Zibal webhook simulation for user {user_id}: {full_command_text}")

    # Simplified parsing for simulation via command
    # Real webhook would be POST request with JSON body or form data
    track_id_match = re.search(r"trackId=(\d+)", full_command_text)
    status_match = re.search(r"status=(\d+)", full_command_text)
    success_match = re.search(r"success=(\d)", full_command_text)

    track_id_param: Optional[int] = int(track_id_match.group(1)) if track_id_match else None
    status_param: Optional[int] = int(status_match.group(1)) if status_match else None
    success_param: Optional[int] = int(success_match.group(1)) if success_match else None # 0 or 1

    if track_id_param is None or status_param is None or success_param is None:
        logger.error(f"Could not parse trackId, status, or success from Zibal webhook simulation: {full_command_text}")
        await update.message.reply_text("Webhook format error.")
        return

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=full_command_text, # The full command text
        message_type="command_webhook_simulation", # Differentiate from "text" or "voice"
        extracted_parameters={
            "track_id": track_id_param,
            "status": status_param,
            "success": bool(success_param) # Convert 0/1 to False/True
        },
        current_intent="intent_payment_callback_process", # Pre-set intent for processing payment callback
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=None, conversation_history=[],
        nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )

    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after handle_zibal_webhook for user {user_id}")

# General Message and Voice Handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user or not update.effective_chat:
        logger.warning("handle_message received an update without message, text, user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_text = update.message.text

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=user_text,
        message_type="text",
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=None, conversation_history=[], current_intent=None,
        extracted_parameters={}, nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after handle_message for user {user_id}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice or not update.effective_user or not update.effective_chat:
        logger.warning("handle_voice received an update without message, voice, user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    transcribed_text: Optional[str] = None

    try:
        # Use the voice_utils.py implementation for voice processing
        from src.voice_utils import process_voice_message
        
        # This will handle downloading, transcribing, and cleaning up the file
        transcribed_text = await process_voice_message(update, context)
        
        if not transcribed_text:
            await update.message.reply_text("متاسفانه نتوانستم صدای شما را تشخیص دهم. لطفاً دوباره تلاش کنید یا متن خود را تایپ کنید.")
            return
            
        logger.info(f"Voice message successfully transcribed for user {user_id}: '{transcribed_text}'")
        
    except Exception as e:
        logger.error(f"Error processing voice message for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(MSG_ERROR_GENERIC)
        return

    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=transcribed_text, # Use the transcribed text as input
        message_type="voice",
        transcribed_text=transcribed_text,
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        conversation_history=[], current_intent=None,
        extracted_parameters={}, nlu_direct_output=None, reminder_creation_context={},
        reminder_filters={}, active_reminders_page=0, payment_context={},
        user_profile=None, current_operation_status=None, response_text=None,
        response_keyboard_markup=None, error_message=None, messages=[]
    )
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after handle_voice for user {user_id}")

# Reminder DB Operations (Python 3.9 Type Hint Corrected)
async def save_or_update_reminder_in_db(
    user_id: int, 
    chat_id: int, 
    context_data: Dict[str, Any], 
    reminder_id_to_update: Optional[int] = None
) -> Tuple[Optional[Reminder], Optional[str]]:
    """
    Saves a new reminder or updates an existing one in the database.
    Now directly fetches the User object using user_id.
    This function is legacy and its logic should be moved to LangGraph nodes.
    For now, it might be called by legacy ConversationHandler states if they are still active.
    """
    logger.warning("Legacy save_or_update_reminder_in_db called. This logic should be in LangGraph.")
    db: Session = next(get_db())
    try:
        # Fetch the User database object using the Telegram user_id
        user_db_obj = db.query(User).filter(User.user_id == user_id).first()
        if not user_db_obj:
            logger.error(f"User with telegram_user_id {user_id} not found in DB. Cannot save/update reminder.")
            return None, "User not found."
        user_db_id = user_db_obj.id # Get the primary key of the User table

        task_description = context_data.get('task_description')
        due_datetime_utc = context_data.get('due_datetime_utc')
        recurrence_rule = context_data.get('recurrence_rule') # e.g., "daily", "weekly"

        if not task_description or not due_datetime_utc:
            return None, "Task description or due datetime missing."

        # Tier limit check - this logic should also be in the graph (load_user_profile_node)
        active_reminder_count = db.query(func.count(Reminder.id)).filter(
            Reminder.user_db_id == user_db_id, 
            Reminder.is_active == True
        ).scalar() or 0
        
        max_reminders = settings.MAX_REMINDERS_PREMIUM_TIER if user_db_obj.is_premium else settings.MAX_REMINDERS_FREE_TIER

        if not reminder_id_to_update and active_reminder_count >= max_reminders:
            return None, MSG_REMINDER_LIMIT_REACHED_FREE if not user_db_obj.is_premium else MSG_REMINDER_LIMIT_REACHED_PREMIUM

        if reminder_id_to_update:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id_to_update, Reminder.user_db_id == user_db_id).first()
            if not reminder:
                return None, "Reminder not found or access denied."
            reminder.task_description = task_description
            reminder.due_datetime_utc = due_datetime_utc
            reminder.recurrence_rule = recurrence_rule
            reminder.updated_at_utc = datetime.datetime.now(pytz.utc)
            reminder.is_sent = False # Reset sent status on update
            logger.info(f"Updated reminder ID {reminder_id_to_update} for user_db_id {user_db_id}")
        else:
            reminder = Reminder(
                user_db_id=user_db_id,
                telegram_user_id=user_id, # Store original telegram user ID as well
                chat_id=chat_id,
                task_description=task_description,
                due_datetime_utc=due_datetime_utc,
                recurrence_rule=recurrence_rule,
                is_active=True,
                is_sent=False
            )
            db.add(reminder)
            logger.info(f"Created new reminder for user_db_id {user_db_id}")
        
        db.commit()
        db.refresh(reminder)
        return reminder, None # Success

    except Exception as e:
        db.rollback()
        logger.error(f"Error in save_or_update_reminder_in_db for user {user_id}: {e}", exc_info=True)
        return None, str(e)
    finally:
        db.close()

# Conversation Handlers
async def handle_initial_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: 
    logger.warning("Legacy ConversationHandler state: handle_initial_message called. Should be handled by LangGraph.")
    await update.message.reply_text("این بخش از ربات در حال بروزرسانی است. لطفا از دستورات اصلی استفاده کنید.")
    return ConversationHandler.END

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.warning("Legacy ConversationHandler state: received_task_description called. Should be handled by LangGraph.")
    await update.message.reply_text("این بخش از ربات در حال بروزرسانی است. لطفا از دستورات اصلی استفاده کنید.")
    return ConversationHandler.END

async def received_full_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.warning("Legacy ConversationHandler state: received_full_datetime called. Should be handled by LangGraph.")
    await update.message.reply_text("این بخش از ربات در حال بروزرسانی است. لطفا از دستورات اصلی استفاده کنید.")
    return ConversationHandler.END

async def received_time_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.warning("Legacy ConversationHandler state: received_time_only called. Should be handled by LangGraph.")
    await update.message.reply_text("این بخش از ربات در حال بروزرسانی است. لطفا از دستورات اصلی استفاده کنید.")
    return ConversationHandler.END

async def received_am_pm_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.warning("Legacy ConversationHandler state: received_am_pm_clarification called. Should be handled by LangGraph.")
    # This function might have had logic to process AM/PM from context.user_data
    # Now, such clarifications are handled within the LangGraph flow.
    await update.message.reply_text("این بخش از ربات در حال بروزرسانی است. لطفا از دستورات اصلی استفاده کنید.")
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline buttons."""
    if not update.callback_query or not update.effective_user or not update.effective_chat:
        logger.warning("button_callback received an update without callback_query, user or chat.")
        return

    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    callback_data = query.data
    
    logger.info(f"Received callback '{callback_data}' from user {user_id}")
    
    # Acknowledge the button press by sending an empty response
    await query.answer()
    
    # Extract the task and date from the confirmation message text
    reminder_ctx = {}
    reminder_text = query.message.text if query.message and query.message.text else ""
    
    # Look for task and datetime in the confirmation message
    import re
    import datetime
    import pytz
    
    task_match = re.search(r'برای «(.+?)»', reminder_text)
    date_match = re.search(r'در تاریخ «(.+?)»', reminder_text)
    
    if callback_data.startswith("confirm_create_reminder:") and task_match and date_match:
        # Only populate for confirmation buttons
        task = task_match.group(1)
        date_str = date_match.group(1)
        logger.info(f"Extracted from confirmation: Task='{task}', Date='{date_str}'")
        
        # Try to parse the datetime string from the confirmation message
        try:
            # For demonstration, create a fixed datetime for tomorrow at 14:00
            # In a real system, you would use the actual datetime from the message
            tomorrow = datetime.datetime.now(pytz.timezone('Asia/Tehran')) + datetime.timedelta(days=1)
            tomorrow = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
            parsed_utc_datetime = tomorrow.astimezone(pytz.utc)
            logger.info(f"Using parsed datetime: {parsed_utc_datetime}")
            
            # Store in context
            reminder_ctx = {
                "collected_task": task,
                "collected_parsed_datetime_utc": parsed_utc_datetime,
                "confirmation_question_text": reminder_text,
                "status": "awaiting_confirmation"
            }
        except Exception as e:
            logger.error(f"Error parsing datetime for confirmation: {e}")
            reminder_ctx = {
                "collected_task": task,
                "confirmation_question_text": reminder_text,
                "status": "awaiting_confirmation"
            }
        
        # Add the pending confirmation type based on the callback
        if callback_data == "confirm_create_reminder:yes":
            pending_confirmation = "create_reminder"
        else:
            pending_confirmation = None
    else:
        pending_confirmation = None
    
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=callback_data,
        message_type="callback_query",
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=None, 
        conversation_history=[], 
        current_intent=None,
        extracted_parameters={}, 
        nlu_direct_output=None, 
        reminder_creation_context=reminder_ctx,
        pending_confirmation=pending_confirmation,
        reminder_filters={}, 
        active_reminders_page=0, 
        payment_context={},
        user_profile=None, 
        current_operation_status=None, 
        response_text=None,
        response_keyboard_markup=None, 
        error_message=None, 
        messages=[]
    )
    
    await _handle_graph_invocation(update, context, initial_state, is_callback=True)
    log_memory_usage(f"after button_callback for user {user_id}")

def main() -> None:
    """Start the bot."""
    init_db()
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    # application.add_handler(CommandHandler("help", help_command)) # Help is handled by graph or direct message
    application.add_handler(CommandHandler("pay", payment_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    # Temporarily commented out undefined handlers
    # application.add_handler(CommandHandler("reminders", reminders_command))
    # application.add_handler(CommandHandler("cancel", cancel_command))
    # Webhook simulation command for testing payment callbacks
    application.add_handler(CommandHandler("zibal_webhook", handle_zibal_webhook)) 

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # General callback handler for all inline buttons, invokes LangGraph
    application.add_handler(CallbackQueryHandler(button_callback))

    # Temporarily commented out undefined job
    # if application.job_queue:
    #     application.job_queue.run_repeating(check_reminders, interval=60, first=10)
    # else:
    #     logger.warning("Job queue is not available. Reminder checks will not run.")

    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()