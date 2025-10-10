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

# Updated import for PTB v22+
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes
)
from telegram.ext import filters
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

# Assuming config.py defines necessary constants like MSG_HELP, etc.
# and settings are imported from config.config
from config.config import settings # For settings like API keys, PAYMENT_AMOUNT
from config.config import MSG_ERROR_GENERIC, MSG_WELCOME # Import all needed messages
# It's recommended to move message constants to a dedicated config/messages.py or include them in config.config.py

from src.database import init_db, get_db
from src.models import Reminder, User, SubscriptionTier
from src.payment import create_payment_link, verify_payment, is_user_premium, PaymentStatus, StripePaymentError, handle_stripe_webhook
from src.datetime_utils import format_datetime_for_display
from src.admin import is_user_admin, set_user_admin, get_user_stats, send_admin_notification

# Import the LangGraph app
from src.graph import lang_graph_app
from src.graph_state import AgentState # For type hinting initial state

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

# Global variable to store the application instance for notification sending
_application_instance = None

def log_memory_usage(context_info: str = ""):
    """Log current memory usage for debugging."""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        logger.debug(f"Memory usage {context_info}: {memory_mb:.1f} MB")
    except ImportError:
        pass  # psutil not available, skip logging

async def _handle_graph_invocation(
    update_obj: Union[Update, None],
    context: ContextTypes.DEFAULT_TYPE,
    initial_state: AgentState,
    is_callback: bool = False,
    is_start_command: bool = False # Added flag for start command
) -> None:
    """
    Centralized function to handle LangGraph invocation with proper error handling.
    """
    try:
        # Log memory before graph invocation
        log_memory_usage(f"before graph invocation for user {initial_state.get('user_id')}")
        
        # Invoke the LangGraph
        result = await lang_graph_app.ainvoke(initial_state)
        
        # Extract response from result
        response_text = result.get('response_text', '')
        response_keyboard_markup = result.get('response_keyboard_markup')
        error_message = result.get('error_message')
        
        # Send response if we have an update object
        if update_obj and (response_text or error_message):
            if is_callback and update_obj.callback_query:
                # For confirmation callbacks, send a new message instead of editing
                callback_data = update_obj.callback_query.data
                if callback_data and callback_data.startswith("confirm_create_reminder:"):
                    # Keep the original confirmation message and send a new response message
                    if error_message:
                        await update_obj.callback_query.message.reply_text(
                            text=error_message,
                            reply_markup=response_keyboard_markup
                        )
                    elif response_text:
                        await update_obj.callback_query.message.reply_text(
                            text=response_text,
                            reply_markup=response_keyboard_markup
                        )
                else:
                    # For other callbacks (like snooze, done), edit the message
                    if error_message:
                        await update_obj.callback_query.edit_message_text(
                            text=error_message,
                            reply_markup=response_keyboard_markup
                        )
                    elif response_text:
                        await update_obj.callback_query.edit_message_text(
                            text=response_text,
                            reply_markup=response_keyboard_markup
                        )
            elif update_obj.message:
                # For regular messages, send new message
                if error_message:
                    await update_obj.message.reply_text(
                        text=error_message,
                        reply_markup=response_keyboard_markup
                    )
                elif response_text:
                    await update_obj.message.reply_text(
                        text=response_text,
                        reply_markup=response_keyboard_markup
                    )
        
        # Log memory after graph invocation
        log_memory_usage(f"after graph invocation for user {initial_state.get('user_id')}")
        
        # Force garbage collection to free memory
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error in _handle_graph_invocation for user {initial_state.get('user_id')}: {e}", exc_info=True)
        
        # Send error message to user
        error_msg = MSG_ERROR_GENERIC
        if update_obj and update_obj.message:
            await update_obj.message.reply_text(error_msg)
        elif update_obj and update_obj.callback_query:
            await update_obj.callback_query.edit_message_text(error_msg)

def create_persistent_keyboard() -> ReplyKeyboardMarkup:
    """Create a persistent reply keyboard with main bot functions."""
    keyboard = [
        [KeyboardButton("My Reminders")],
        [KeyboardButton("Unlimited Reminders 👑")],
        [KeyboardButton("Settings")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.effective_user or not update.effective_chat:
        logger.warning("start_command received an update without user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Received /start from user {user_id}")
    
    # Check if user has timezone set
    db: Session = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if user and user.timezone and user.timezone != 'UTC':
            # User has timezone set, send normal welcome
            keyboard = create_persistent_keyboard()
            welcome_message = (
                "Hello 👋\n"
                "Welcome to the Reminder Bot!\n\n"
                "Just send me a message or voice and tell me what to remind you about and when. For example:\n"
                "🗓 \"Remind me to call mom tomorrow at 3pm\"\n"
                "💊 \"Remind me to take my pills every day at 8am\"\n\n"
                "✨ Bot Features:\n"
                "- Create reminders by speaking or typing\n"
                "- Smart detection of date and time from your message\n"
                "- View and delete active reminders\n"
                "- Timezone support for accurate scheduling\n"
                "- Premium features available\n\n"
                "Use the keyboard below to access bot features:"
            )
            
            await update.message.reply_text(
                welcome_message,
                reply_markup=keyboard
            )
        else:
            # User needs to set timezone first - show bot introduction first
            intro_message = (
                "🎉 **Welcome to the Reminder Bot!** 👋\n\n"
                "I'm your personal AI assistant that helps you never forget important tasks and appointments!\n\n"
                "✨ **What I can do:**\n"
                "• Create reminders by typing or speaking\n"
                "• Smart time detection (\"tomorrow at 3pm\", \"every Monday 9am\")\n"
                "• View and manage your reminders\n"
                "• Send notifications with snooze options\n"
                "• Support for recurring reminders\n\n"
                "🔔 **Example commands:**\n"
                "• \"Remind me to call mom tomorrow at 3pm\"\n"
                "• \"Remind me to take medicine every day at 8am\"\n"
                "• \"Remind me about the meeting on Friday at 2pm\"\n\n"
                "⏰ **Why timezone matters:**\n"
                "Setting your timezone ensures your reminders are triggered at the correct local time. "
                "For example, if you're in New York and set a reminder for \"3pm\", it will notify you at 3pm New York time, not UTC time.\n\n"
                "Let's set up your timezone first:"
            )
            
            keyboard = [
                [InlineKeyboardButton("📍 Send Location (Recommended)", callback_data="timezone_send_location")],
                [InlineKeyboardButton("🏙️ Enter City Name", callback_data="timezone_enter_city")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                intro_message,
                reply_markup=reply_markup
            )
            
            # Set flag to indicate user needs to set timezone
            context.user_data['needs_timezone_setup'] = True
            
            # Create user if they don't exist yet
            if not user:
                user = User(
                    telegram_id=user_id,
                    username=update.effective_user.username,
                    first_name=update.effective_user.first_name,
                    last_name=update.effective_user.last_name,
                    language_code=update.effective_user.language_code,
                    timezone='UTC'  # Default timezone
                )
                db.add(user)
                db.commit()
                logger.info(f"Created new user {user_id} during timezone setup")
                
                # Send admin notification for new user registration
                try:
                    await send_admin_notification(update.get_bot(), user, "new_user")
                except Exception as e:
                    logger.error(f"Failed to send admin notification for new user {user_id}: {e}")
            
    except Exception as e:
        logger.error(f"Error checking user timezone in start command: {e}")
        # Fallback to normal welcome
        keyboard = create_persistent_keyboard()
        welcome_message = (
            "Hello 👋\n"
            "Welcome to the Reminder Bot!\n\n"
            "Just send me a message or voice and tell me what to remind you about and when. For example:\n"
            "🗓 \"Remind me to call mom tomorrow at 3pm\"\n"
            "💊 \"Remind me to take my pills every day at 8am\"\n\n"
            "✨ Bot Features:\n"
            "- Create reminders by speaking or typing\n"
            "- Smart detection of date and time from your message\n"
            "- View and delete active reminders\n"
            "- Timezone support for accurate scheduling\n"
            "- Premium features available\n\n"
            "Use the keyboard below to access bot features:"
        )
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=keyboard
        )
    finally:
        db.close()
    
    log_memory_usage(f"after start_command for user {user_id}")

async def payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pay command."""
    if not update.effective_user or not update.effective_chat:
        logger.warning("payment_command received an update without user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Received /pay from user {user_id}")
    
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text="/pay",
        message_type="command",
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
        reminder_creation_context={}, 
        pending_confirmation=None,
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
    
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after payment_command for user {user_id}")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /privacy command - redirects to settings privacy policy."""
    await handle_settings_privacy_policy_callback(update, context)

async def handle_stripe_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stripe_webhook command (simulated webhook for testing)."""
    if not update.effective_user or not update.effective_chat:
        logger.warning("handle_stripe_webhook received an update without user or chat.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Received /stripe_webhook from user {user_id}")
    
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text="/stripe_webhook",
        message_type="command",
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
        reminder_creation_context={}, 
        pending_confirmation=None,
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
    
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after handle_stripe_webhook for user {user_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    if not update.effective_user or not update.effective_chat or not update.message or not update.message.text:
        logger.warning("handle_message received an update without user, chat, or text.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Skip processing if this is a command (should be handled by CommandHandler)
    if text.startswith('/'):
        logger.info(f"Skipping command '{text}' in handle_message - should be handled by CommandHandler")
        return
    
    logger.info(f"Received text message from user {user_id}: {text[:50]}...")
    
    # Handle account deletion confirmation
    if context.user_data.get('waiting_for_delete_confirmation'):
        expected_message = context.user_data.get('delete_confirmation_message', '')
        if text == expected_message:
            # User confirmed deletion
            db = next(get_db())
            success = await delete_user_account(user_id, db)
            if success:
                # Clear the deletion flags
                context.user_data.pop('waiting_for_delete_confirmation', None)
                context.user_data.pop('delete_confirmation_message', None)
                
                deletion_success_text = (
                    "✅ **Account Deleted Successfully**\n\n"
                    "Your account and all associated data have been permanently deleted.\n\n"
                    "• All reminders have been removed\n"
                    "• Your profile has been deleted\n"
                    "• Your subscription has been cancelled\n\n"
                    "Thank you for using our service. You can start fresh anytime by using /start again."
                )
                
                keyboard = create_persistent_keyboard()
                await update.message.reply_text(deletion_success_text, reply_markup=keyboard)
            else:
                error_text = (
                    "❌ **Deletion Failed**\n\n"
                    "There was an error deleting your account. Please try again or contact support."
                )
                keyboard = [
                    [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(error_text, reply_markup=reply_markup)
        else:
            # User typed something else, cancel deletion
            context.user_data.pop('waiting_for_delete_confirmation', None)
            context.user_data.pop('delete_confirmation_message', None)
            
            cancel_text = (
                "✅ **Deletion Cancelled**\n\n"
                "Your account has not been deleted. All your data remains safe.\n\n"
                "You can continue using the bot normally."
            )
            
            keyboard = create_persistent_keyboard()
            await update.message.reply_text(cancel_text, reply_markup=keyboard)
        return
    
    # Handle keyboard button presses
    if text == "Settings":
        await handle_settings_button(update, context)
        return
    elif text == "Help":
        await handle_help_button(update, context)
        return

    elif text == "My Reminders":
        # Let this go through the normal message flow to be handled by LangGraph
        pass
    elif text == "Unlimited Reminders 👑":
        # Let this go through the normal message flow to be handled by LangGraph
        pass
    
    # Check if user is in city name input mode
    if context.user_data.get('waiting_for_city_name'):
        # If user types "Back to Settings", clear the flag and go back to settings
        if text == "Back to Settings":
            context.user_data['waiting_for_city_name'] = False
            await handle_settings_button(update, context)
            return
        # If user types "Back to Timezone Settings", clear the flag and go back to timezone options
        elif text == "Back to Timezone Settings":
            context.user_data['waiting_for_city_name'] = False
            await handle_change_timezone_button(update, context)
            return
        # Otherwise, treat the text as a city name
        context.user_data['waiting_for_city_name'] = False
        await handle_city_name_input(update, context)
        return
    
    # Get session ID for conversation memory
    from src.conversation_memory import conversation_memory
    session_id = conversation_memory.get_session_id(user_id, chat_id)
    
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=text,
        message_type="text",
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
        reminder_creation_context={}, 
        pending_confirmation=None,
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
    
    await _handle_graph_invocation(update, context, initial_state)
    
    # Save user message to conversation memory after graph processing
    # This allows the graph to clear the memory if needed (e.g., for clarifications)
    conversation_memory.add_user_message(session_id, text)
    
    log_memory_usage(f"after handle_message for user {user_id}")

async def handle_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Settings button press."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Settings button pressed by user {user_id}")
    
    # Get user from database
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        await update.message.reply_text("User not found. Please use /start to register.")
        return
    
    # Create settings inline keyboard
    keyboard = [
        [InlineKeyboardButton("Change Timezone", callback_data="settings_change_timezone")],
        [InlineKeyboardButton("Privacy Policy", callback_data="settings_privacy_policy")],
        [InlineKeyboardButton("Terms of Service", callback_data="settings_terms_of_service")],
        [InlineKeyboardButton("Contact Me", callback_data="settings_contact_me")],
        [InlineKeyboardButton("🗑️ Delete Account", callback_data="settings_delete_account")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="settings_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_timezone = user.timezone or "UTC"
    # Get display name for timezone
    from src.timezone_utils import get_timezone_display_name
    timezone_display = get_timezone_display_name(current_timezone)
    
    settings_text = f"🔧 Settings\n\nCurrent timezone: {timezone_display}\n\nSelect an option:"
    
    await update.message.reply_text(settings_text, reply_markup=reply_markup)

async def handle_help_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Help button press."""
    help_text = (
        "🤖 **Reminder Bot Help**\n\n"
        "**Commands:**\n"
        "• Send text or voice messages to create reminders\n"
        "• Use the keyboard buttons for quick access\n\n"
        "**Examples:**\n"
        "• \"Remind me to call mom tomorrow at 3pm\"\n"
        "• \"Meeting with team on Friday at 10am\"\n"
        "• \"Take medicine every day at 8am\"\n\n"
        "**Features:**\n"
        "• Voice message support\n"
        "• Recurring reminders\n"
        "• Timezone support\n"
        "• Premium features available"
    )
    
    keyboard = create_persistent_keyboard()
    await update.message.reply_text(help_text, reply_markup=keyboard)



async def handle_change_timezone_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Change Timezone button press."""
    user_id = update.effective_user.id
    
    logger.info(f"Change Timezone button pressed by user {user_id}")
    
    # Create timezone selection inline keyboard
    keyboard = [
        [InlineKeyboardButton("📍 Send Location", callback_data="timezone_send_location")],
        [InlineKeyboardButton("🏙️ Enter City Name", callback_data="timezone_enter_city")],
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    timezone_text = (
        "🌍 Change Timezone\n\n"
        "You can set your timezone in two ways:\n\n"
        "📍 Send Location - Share your location to automatically detect timezone\n"
        "🏙️ Enter City Name - Type a city name (e.g., 'New York', 'London', 'Tokyo')\n\n"
        "Select an option:"
    )
    
    await update.message.reply_text(timezone_text, reply_markup=reply_markup)

async def handle_back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Back to Main Menu button press."""
    keyboard = create_persistent_keyboard()
    await update.message.reply_text("Back to main menu:", reply_markup=keyboard)

async def handle_back_to_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Back to Settings button press."""
    await handle_settings_button(update, context)

async def handle_send_location_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Send Location button press."""
    keyboard = [
        [KeyboardButton("📍 Share Location", request_location=True)],
        [KeyboardButton("Back to Timezone Settings")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📍 Please share your location to automatically detect your timezone:",
        reply_markup=reply_markup
    )

async def handle_enter_city_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Enter City Name button press."""
    # Set flag to indicate we're waiting for city name input
    context.user_data['waiting_for_city_name'] = True
    
    keyboard = [
        [KeyboardButton("Back to Timezone Settings")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "🏙️ Please type a city name (e.g., 'New York', 'London', 'Tokyo'):\n\nYou can also share your location instead by clicking the button below.",
        reply_markup=reply_markup
    )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle location sharing for timezone detection."""
    user_id = update.effective_user.id
    
    if not update.message.location:
        await update.message.reply_text("No location received. Please try again.")
        return
    
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    
    logger.info(f"Location received from user {user_id}: ({lat}, {lon})")
    
    # Get timezone from location
    from src.timezone_utils import get_timezone_from_location, get_timezone_display_name
    
    timezone = get_timezone_from_location(lat, lon)
    
    if timezone:
        # Save timezone to user profile
        db = next(get_db())
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if user:
            user.timezone = timezone
            db.commit()
            
            display_name = get_timezone_display_name(timezone)
            
            # Check if this was the initial timezone setup
            if context.user_data.get('needs_timezone_setup'):
                # Clear the flag
                context.user_data['needs_timezone_setup'] = False
                
                # Show welcome message after timezone setup
                welcome_message = (
                    f"✅ **Perfect! Your timezone is set to: {display_name}**\n\n"
                    f"🎉 **You're all set!** Your Reminder Bot is ready to help you stay organized.\n\n"
                    f"🚀 **Get started:**\n"
                    f"• Type or speak your reminders naturally\n"
                    f"• Use the keyboard buttons below for quick access\n"
                    f"• Try: \"Remind me to call mom tomorrow at 3pm\"\n\n"
                    f"💡 **Pro tip:** You can also use voice messages for hands-free reminder creation!\n\n"
                    f"Use the keyboard below to explore all features:"
                )
                
                keyboard = create_persistent_keyboard()
                await update.message.reply_text(welcome_message, reply_markup=keyboard)
            else:
                # Normal timezone update
                success_text = f"✅ Timezone updated successfully!\n\nYour timezone is now: {display_name}"
                keyboard = create_persistent_keyboard()
                await update.message.reply_text(success_text, reply_markup=keyboard)
        else:
            await update.message.reply_text("User not found. Please use /start to register.")
    else:
        error_text = "❌ Could not detect timezone from your location. Please try entering a city name instead."
        keyboard = [
            [KeyboardButton("Enter City Name")],
            [KeyboardButton("Back to Settings")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(error_text, reply_markup=reply_markup)

async def handle_city_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle city name input for timezone detection."""
    user_id = update.effective_user.id
    city_name = update.message.text.strip()
    
    logger.info(f"City name received from user {user_id}: {city_name}")
    
    # Get timezone from city name using Gemini
    from src.timezone_utils import get_timezone_from_city_gemini, get_timezone_display_name
    
    timezone = get_timezone_from_city_gemini(city_name)
    
    if timezone:
        # Save timezone to user profile
        db = next(get_db())
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if user:
            user.timezone = timezone
            db.commit()
            
            display_name = get_timezone_display_name(timezone)
            
            # Check if this was the initial timezone setup
            if context.user_data.get('needs_timezone_setup'):
                # Clear the flag
                context.user_data['needs_timezone_setup'] = False
                
                # Show welcome message after timezone setup
                welcome_message = (
                    f"✅ **Perfect! Your timezone is set to: {display_name}**\n\n"
                    f"🎉 **You're all set!** Your Reminder Bot is ready to help you stay organized.\n\n"
                    f"🚀 **Get started:**\n"
                    f"• Type or speak your reminders naturally\n"
                    f"• Use the keyboard buttons below for quick access\n"
                    f"• Try: \"Remind me to call mom tomorrow at 3pm\"\n\n"
                    f"💡 **Pro tip:** You can also use voice messages for hands-free reminder creation!\n\n"
                    f"Use the keyboard below to explore all features:"
                )
                
                keyboard = create_persistent_keyboard()
                await update.message.reply_text(welcome_message, reply_markup=keyboard)
            else:
                # Normal timezone update
                success_text = f"✅ Timezone updated successfully!\n\nYour timezone is now: {display_name}"
                keyboard = create_persistent_keyboard()
                await update.message.reply_text(success_text, reply_markup=keyboard)
        else:
            await update.message.reply_text("User not found. Please use /start to register.")
    else:
        error_text = f"❌ Could not find the city '{city_name}'.\n\nPlease try typing a different city name (e.g., 'New York', 'London', 'Tokyo', 'Paris').\n\nOr you can share your location instead."
        
        # Set flag to indicate we're still waiting for city name input
        context.user_data['waiting_for_city_name'] = True
        
        keyboard = [
            [KeyboardButton("📍 Share Location", request_location=True)],
            [KeyboardButton("Back to Settings")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(error_text, reply_markup=reply_markup)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice messages."""
    if not update.effective_user or not update.effective_chat or not update.message or not update.message.voice:
        logger.warning("handle_voice received an update without user, chat, or voice.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Received voice message from user {user_id}")
    
    # Download and transcribe voice message
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        
        # Create temporary file for voice
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            voice_data = await voice_file.download_as_bytearray()
            temp_file.write(voice_data)
            temp_file_path = temp_file.name
        
        # Transcribe using Google Speech-to-Text
        from src.voice_utils import transcribe_english_voice
        transcribed_text = transcribe_english_voice(temp_file_path)
        
        # Note: transcribe_english_voice handles file cleanup in its finally block
        
        if transcribed_text:
            logger.info(f"Transcribed voice message from user {user_id}: {transcribed_text[:50]}...")
        else:
            logger.warning(f"Failed to transcribe voice message from user {user_id}")
            await update.message.reply_text("Sorry, I could not recognize your voice message. Please try again or use text input.")
            return
            
    except Exception as e:
        logger.error(f"Error processing voice message from user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Error processing voice message. Please try again.")
        return
    
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=transcribed_text,
        message_type="voice",
        user_telegram_details = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "language_code": update.effective_user.language_code
        },
        transcribed_text=transcribed_text, 
        conversation_history=[], 
        current_intent=None,
        extracted_parameters={}, 
        nlu_direct_output=None, 
        reminder_creation_context={}, 
        pending_confirmation=None,
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
    
    await _handle_graph_invocation(update, context, initial_state)
    log_memory_usage(f"after handle_voice for user {user_id}")



# NEW: Reminder Notification System
async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background job to check for due reminders and send notifications.
    This function runs every minute to check for reminders that are due.
    """
    global _application_instance
    
    if not _application_instance:
        logger.warning("Application instance not available for sending notifications")
        return
    
    logger.info("Checking for due reminders...")
    
    db: Session = next(get_db())
    try:
        # Get current time in UTC
        now_utc = datetime.datetime.now(pytz.utc)
        
        # Find all active reminders that are due (past due time)
        # Query for due reminders
        due_reminders = db.query(Reminder).join(User).filter(
            and_(
                Reminder.is_active == True,
                Reminder.is_notified == False,
                Reminder.due_datetime_utc <= now_utc
            )
        ).all()
        
        logger.info(f"Found {len(due_reminders)} due reminders")
        
        for reminder in due_reminders:
            try:
                # Get user information
                user = reminder.user
                if not user:
                    logger.warning(f"Reminder {reminder.id} has no associated user, skipping")
                    continue
                
                # Send notification
                notification_sent = await send_reminder_notification(
                    context, 
                    user.telegram_id, 
                    user.chat_id or user.telegram_id, 
                    reminder
                )
                
                if notification_sent:
                    # Mark reminder as notified
                    reminder.is_notified = True
                    reminder.notification_sent_at = now_utc
                    
                    # Handle recurring reminders
                    if reminder.recurrence_rule:
                        await handle_recurring_reminder(reminder, db)
                    else:
                        # For non-recurring reminders, mark as inactive
                        reminder.is_active = False
                    
                    db.commit()
                    logger.info(f"Reminder {reminder.id} notification sent and status updated")
                else:
                    logger.error(f"Failed to send notification for reminder {reminder.id}")
                    
            except Exception as e:
                logger.error(f"Error processing reminder {reminder.id}: {e}", exc_info=True)
                db.rollback()
                continue
                
    except Exception as e:
        logger.error(f"Error in check_and_send_reminders: {e}", exc_info=True)
    finally:
        db.close()

async def send_reminder_notification(
    context: ContextTypes.DEFAULT_TYPE, 
    user_id: int, 
    chat_id: int, 
    reminder: Reminder
) -> bool:
    """
    Send a reminder notification to the user.
    Returns True if notification was sent successfully, False otherwise.
    """
    try:
        # Create notification message
        message_text = f"🔔 Reminder:\n{reminder.task}"
        
        # Add buttons for all reminders (both recurring and one-time)
        keyboard = [
            [
                InlineKeyboardButton("⏰ Snooze 15 min", callback_data=f"snooze:{reminder.id}:15"),
                InlineKeyboardButton("⏰ Snooze 1 hour", callback_data=f"snooze:{reminder.id}:60")
            ],
            [
                InlineKeyboardButton("✅ Mark as done", callback_data=f"done:{reminder.id}")
            ]
        ]
        
        # Add special note for recurring reminders with next due date
        if reminder.recurrence_rule:
            # Calculate next due date for display
            user_timezone = 'UTC'
            if reminder.user and getattr(reminder.user, 'timezone', None):
                user_timezone = reminder.user.timezone
            next_due = calculate_next_recurrence(reminder.due_datetime_utc, reminder.recurrence_rule, user_timezone)
            next_due_str = format_datetime_for_display(next_due, user_timezone)
            
            if reminder.recurrence_rule.lower() == "daily":
                recurrence_text = "daily"
            elif reminder.recurrence_rule.lower() == "weekly":
                recurrence_text = "weekly"
            elif reminder.recurrence_rule.lower() == "monthly":
                recurrence_text = "monthly"
            else:
                recurrence_text = reminder.recurrence_rule
            
            message_text += f"\n\n🔄 **Recurring Reminder** ({recurrence_text})\n⏰ Next reminder: {next_due_str}"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the notification
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=reply_markup
        )
        
        logger.info(f"Reminder notification sent to user {user_id} for task: {reminder.task}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending reminder notification to user {user_id}: {e}", exc_info=True)
        return False

def calculate_next_recurrence(current_due: datetime.datetime, recurrence_rule: str, user_timezone: str = 'UTC') -> datetime.datetime:
    """
    Calculate the next due date for a recurring reminder in the user's timezone.
    """
    import pytz
    try:
        recurrence = recurrence_rule.lower()
        tz = pytz.timezone(user_timezone) if user_timezone and user_timezone != 'UTC' else pytz.utc
        # Convert current_due to user's local time
        local_due = current_due.astimezone(tz)
        if recurrence == "daily":
            next_local_due = local_due + datetime.timedelta(days=1)
        elif recurrence == "weekly":
            next_local_due = local_due + datetime.timedelta(weeks=1)
        elif recurrence == "monthly":
            # Add one month, handle month overflow
            month = local_due.month + 1
            year = local_due.year
            if month > 12:
                month = 1
                year += 1
            day = min(local_due.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
            try:
                next_local_due = local_due.replace(year=year, month=month, day=day)
            except Exception:
                # fallback: add 30 days
                next_local_due = local_due + datetime.timedelta(days=30)
        else:
            # Unknown recurrence, return current due date
            next_local_due = local_due
        # Convert back to UTC
        return next_local_due.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Error calculating next recurrence: {e}", exc_info=True)
        return current_due

async def handle_recurring_reminder(reminder: Reminder, db: Session) -> None:
    """
    Handle recurring reminders by calculating the next due date.
    """
    try:
        # Calculate next due date
        user_timezone = 'UTC'
        if reminder.user and getattr(reminder.user, 'timezone', None):
            user_timezone = reminder.user.timezone
        next_due = calculate_next_recurrence(reminder.due_datetime_utc, reminder.recurrence_rule, user_timezone)
        
        # Update the reminder with new due date
        reminder.due_datetime_utc = next_due
        reminder.is_notified = False
        reminder.notification_sent_at = None
        
        logger.info(f"Recurring reminder {reminder.id} rescheduled to {next_due}")
        
    except Exception as e:
        logger.error(f"Error handling recurring reminder {reminder.id}: {e}", exc_info=True)
        # If there's an error, mark as inactive to prevent issues
        reminder.is_active = False

async def handle_snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle snooze button callbacks.
    """
    if not update.callback_query:
        return
    
    query = update.callback_query
    callback_data = query.data
    
    if not callback_data.startswith("snooze:"):
        return
    
    try:
        # Parse callback data: snooze:reminder_id:minutes
        parts = callback_data.split(":")
        if len(parts) != 3:
            return
        
        reminder_id = int(parts[1])
        snooze_minutes = int(parts[2])
        
        # Update reminder due time
        db: Session = next(get_db())
        try:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
            if reminder:
                new_due_time = datetime.datetime.now(pytz.utc) + datetime.timedelta(minutes=snooze_minutes)
                reminder.due_datetime_utc = new_due_time
                reminder.is_notified = False
                reminder.notification_sent_at = None
                db.commit()
                
                # Different message for recurring vs one-time reminders
                if reminder.recurrence_rule:
                    await query.answer(f"Recurring reminder snoozed for {snooze_minutes} minutes")
                    await query.edit_message_text(f"⏰ Recurring reminder snoozed for {snooze_minutes} minutes\n\n🔄 This reminder will continue to repeat as scheduled.")
                else:
                    await query.answer(f"Reminder snoozed for {snooze_minutes} minutes")
                    await query.edit_message_text(f"⏰ Reminder snoozed for {snooze_minutes} minutes")
                
                logger.info(f"Reminder {reminder_id} snoozed for {snooze_minutes} minutes")
            else:
                await query.answer("Reminder not found")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error handling snooze callback: {e}", exc_info=True)
        await query.answer("Error setting reminder snooze")

async def handle_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle done button callbacks.
    """
    if not update.callback_query:
        return
    
    query = update.callback_query
    callback_data = query.data
    
    if not callback_data.startswith("done:"):
        return
    
    try:
        # Parse callback data: done:reminder_id
        parts = callback_data.split(":")
        if len(parts) != 2:
            return
        
        reminder_id = int(parts[1])
        
        # Mark reminder as done
        db: Session = next(get_db())
        try:
            reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
            if reminder:
                if reminder.recurrence_rule:
                    # For recurring reminders, calculate next due date and keep it active
                    user_timezone = 'UTC'
                    if reminder.user and getattr(reminder.user, 'timezone', None):
                        user_timezone = reminder.user.timezone
                    next_due = calculate_next_recurrence(reminder.due_datetime_utc, reminder.recurrence_rule, user_timezone)
                    reminder.due_datetime_utc = next_due
                    reminder.is_notified = False
                    reminder.notification_sent_at = None
                    db.commit()
                    
                    # Format next due date for display
                    next_due_str = format_datetime_for_display(next_due, user_timezone)
                    
                    await query.answer("Recurring reminder marked as done for this occurrence")
                    await query.edit_message_text(f"✅ Recurring reminder marked as done for this occurrence\n\n🔄 Next reminder: {next_due_str}")
                    
                    logger.info(f"Recurring reminder {reminder_id} marked as done and rescheduled to {next_due}")
                else:
                    # For one-time reminders, mark as inactive
                    reminder.is_active = False
                    reminder.is_notified = True
                    db.commit()
                    
                    await query.answer("Reminder marked as done")
                    await query.edit_message_text("✅ Reminder completed")
                    
                    logger.info(f"Reminder {reminder_id} marked as done")
            else:
                await query.answer("Reminder not found")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error handling done callback: {e}", exc_info=True)
        await query.answer("Error marking reminder as done")

# Settings and Timezone Callback Handlers
async def handle_settings_change_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Change Timezone button from settings."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"Settings Change Timezone callback from user {user_id}")
    
    # Create timezone selection inline keyboard
    keyboard = [
        [InlineKeyboardButton("📍 Send Location", callback_data="timezone_send_location")],
        [InlineKeyboardButton("🏙️ Enter City Name", callback_data="timezone_enter_city")],
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    timezone_text = (
        "🌍 **Change Timezone**\n\n"
        "You can set your timezone in two ways:\n\n"
        "📍 **Send Location** - Share your location to automatically detect timezone\n"
        "🏙️ **Enter City Name** - Type a city name (e.g., 'New York', 'London', 'Tokyo')\n\n"
        "Select an option:"
    )
    
    await query.edit_message_text(timezone_text, reply_markup=reply_markup, )

async def handle_settings_back_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Back to Main Menu button from settings."""
    query = update.callback_query
    
    await query.edit_message_text("Back to main menu. Use the keyboard buttons below to access bot features.")

async def handle_timezone_send_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Send Location button from timezone settings."""
    query = update.callback_query
    
    await query.edit_message_text(
        "📍 Please share your location to automatically detect your timezone.\n\n"
        "Use the paperclip button to share your location."
    )

async def handle_timezone_enter_city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Enter City Name button from timezone settings."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Set flag to indicate we're waiting for city name input
    context.user_data['waiting_for_city_name'] = True
    
    await query.edit_message_text(
        "🏙️ Please type a city name (e.g., 'New York', 'London', 'Tokyo'):"
    )

async def handle_timezone_back_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Back to Settings button from timezone settings."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Get user from database
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        await query.edit_message_text("User not found. Please use /start to register.")
        return
    
    # Create settings inline keyboard
    keyboard = [
        [InlineKeyboardButton("Change Timezone", callback_data="settings_change_timezone")],
        [InlineKeyboardButton("Privacy Policy", callback_data="settings_privacy_policy")],
        [InlineKeyboardButton("Terms of Service", callback_data="settings_terms_of_service")],
        [InlineKeyboardButton("Contact Me", callback_data="settings_contact_me")],
        [InlineKeyboardButton("🗑️ Delete Account", callback_data="settings_delete_account")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="settings_back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_timezone = user.timezone or "UTC"
    settings_text = f"🔧 **Settings**\n\nCurrent timezone: {current_timezone}\n\nSelect an option:"
    
    await query.edit_message_text(settings_text, reply_markup=reply_markup, )

async def handle_settings_privacy_policy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Privacy Policy button from settings."""
    query = update.callback_query
    
    privacy_text = (
        "🔒 **Privacy Policy**\n\n"
        "Our complete Privacy Policy is available online.\n\n"
        "• We only store your reminders and basic profile info\n"
        "• Voice messages are processed but not stored\n"
        "• Your data is never shared with third parties\n"
        "• You can delete your account anytime\n\n"
        "📖 **Read Full Policy:**\n"
        f"{settings.LEGAL_PAGES_BASE_URL}/privacy\n\n"
        f"For questions, contact us at {settings.SUPPORT_EMAIL}"
    )
    
    keyboard = [
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(privacy_text, reply_markup=reply_markup)

async def handle_settings_terms_of_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Terms of Service button from settings."""
    query = update.callback_query
    
    terms_text = (
        "📋 **Terms of Service**\n\n"
        "Our complete Terms of Service are available online.\n\n"
        "• Free tier: 5 active reminders\n"
        "• Premium tier: Unlimited reminders (€4.99/month)\n"
        "• Full money-back guarantee\n"
        "• Cancel anytime via email or Telegram\n"
        "• Use for lawful purposes only\n\n"
        "📖 **Read Full Terms:**\n"
        f"{settings.LEGAL_PAGES_BASE_URL}/terms\n\n"
        f"For questions, contact us at {settings.SUPPORT_EMAIL}"
    )
    
    keyboard = [
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(terms_text, reply_markup=reply_markup)

async def handle_settings_contact_me_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Contact Me button from settings."""
    query = update.callback_query
    
    contact_text = (
        "📧 **Contact Us**\n\n"
        "We're here to help! Contact us for:\n\n"
        "• Technical support\n"
        "• Privacy questions\n"
        "• Payment issues\n"
        "• Bug reports\n"
        "• Feature requests\n\n"
        f"**Email:** {settings.SUPPORT_EMAIL}\n"
        f"**Telegram:** {settings.SUPPORT_TELEGRAM_ID}\n"
        "**Response Time:** Within 24 hours"
    )
    
    keyboard = [
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(contact_text, reply_markup=reply_markup)

async def handle_settings_delete_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Delete Account button from settings - First confirmation."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    delete_warning_text = (
        "⚠️ **Delete Account - First Confirmation**\n\n"
        "**This action will permanently delete your account and all associated data:**\n\n"
        "🗑️ **What will be deleted:**\n"
        "• All your reminders (active and completed)\n"
        "• Your user profile and settings\n"
        "• Your timezone preferences\n"
        "• Your subscription information\n"
        "• All conversation history\n\n"
        "💾 **What will be preserved:**\n"
        "• Purchase records (for legal compliance)\n"
        "• Payment transaction history\n\n"
        "⚠️ **This action is irreversible!**\n\n"
        "If you're sure you want to proceed, click the button below for the final confirmation."
    )
    
    keyboard = [
        [InlineKeyboardButton("🗑️ I want to delete my account", callback_data="delete_account_confirm")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(delete_warning_text, reply_markup=reply_markup)

async def handle_delete_account_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Delete Account confirmation - Second confirmation."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    final_warning_text = (
        "🚨 **Final Confirmation Required**\n\n"
        "**You are about to permanently delete your account!**\n\n"
        "This is your last chance to cancel. Once confirmed:\n"
        "• All your data will be permanently deleted\n"
        "• You will lose access to all your reminders\n"
        "• Your subscription will be cancelled\n"
        "• This action cannot be undone\n\n"
        "**To finalize the deletion, please type the following message in the chat:**\n"
        "`I confirm I want to delete my account permanently`\n\n"
        "**To cancel, simply ignore this message or type anything else.**"
    )
    
    # Set flag in context to indicate we're waiting for final confirmation
    context.user_data['waiting_for_delete_confirmation'] = True
    context.user_data['delete_confirmation_message'] = "I confirm I want to delete my account permanently"
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel Deletion", callback_data="delete_account_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(final_warning_text, reply_markup=reply_markup)

async def handle_delete_account_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Delete Account cancellation."""
    query = update.callback_query
    
    # Clear the deletion flag
    context.user_data.pop('waiting_for_delete_confirmation', None)
    context.user_data.pop('delete_confirmation_message', None)
    
    cancel_text = (
        "✅ **Deletion Cancelled**\n\n"
        "Your account has not been deleted. All your data remains safe.\n\n"
        "You can continue using the bot normally."
    )
    
    keyboard = [
        [InlineKeyboardButton("Back to Settings", callback_data="timezone_back_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(cancel_text, reply_markup=reply_markup)

async def delete_user_account(user_id: int, db: Session) -> bool:
    """Delete user account and all associated data, preserving purchase records."""
    try:
        # Get user
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            logger.warning(f"Attempted to delete non-existent user: {user_id}")
            return False
        
        logger.info(f"Starting account deletion for user {user_id}")
        
        # Delete all reminders for this user
        reminders_deleted = db.query(Reminder).filter(Reminder.user_id == user.id).delete()
        logger.info(f"Deleted {reminders_deleted} reminders for user {user_id}")
        
        # Delete the user record (this will cascade to other user-related data)
        # Note: We preserve purchase records by not deleting them
        db.delete(user)
        
        # Commit the changes
        db.commit()
        
        logger.info(f"Successfully deleted account for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting account for user {user_id}: {e}")
        db.rollback()
        return False



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
    
    # Handle snooze and done callbacks first (these are handled outside the graph)
    if callback_data.startswith("snooze:"):
        await handle_snooze_callback(update, context)
        return
    elif callback_data.startswith("done:"):
        await handle_done_callback(update, context)
        return
    
    # Handle settings and timezone callbacks (these are handled outside the graph)
    if callback_data == "settings_change_timezone":
        await handle_settings_change_timezone_callback(update, context)
        return
    elif callback_data == "settings_privacy_policy":
        await handle_settings_privacy_policy_callback(update, context)
        return
    elif callback_data == "settings_terms_of_service":
        await handle_settings_terms_of_service_callback(update, context)
        return
    elif callback_data == "settings_contact_me":
        await handle_settings_contact_me_callback(update, context)
        return
    elif callback_data == "settings_delete_account":
        await handle_settings_delete_account_callback(update, context)
        return
    elif callback_data == "delete_account_confirm":
        await handle_delete_account_confirm_callback(update, context)
        return
    elif callback_data == "delete_account_cancel":
        await handle_delete_account_cancel_callback(update, context)
        return
    elif callback_data == "settings_back_main":
        await handle_settings_back_main_callback(update, context)
        return
    elif callback_data == "timezone_send_location":
        await handle_timezone_send_location_callback(update, context)
        return
    elif callback_data == "timezone_enter_city":
        await handle_timezone_enter_city_callback(update, context)
        return
    elif callback_data == "timezone_back_settings":
        await handle_timezone_back_settings_callback(update, context)
        return
    
    # Acknowledge the button press by sending an empty response
    await query.answer()
    
    # For all other callbacks (including reminder confirmations), pass to the graph
    # The graph will handle the callback processing logic
    initial_state = AgentState(
        user_id=user_id,
        chat_id=chat_id,
        input_text=callback_data,
        message_type="callback_query",
        user_telegram_details={
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
        reminder_creation_context={},
        pending_confirmation=None,
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

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received /ping from user {update.effective_user.id if update.effective_user else 'unknown'}")
    await update.message.reply_text("pong")

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot version information."""
    try:
        from src.version import VERSION_INFO
        response_text = (
            f"🤖 **Bot Version Information**\n\n"
            f"**Version:** {VERSION_INFO['version']}\n"
            f"**Commit:** {VERSION_INFO['commit_hash']}\n"
            f"**Message:** {VERSION_INFO['commit_message']}\n"
            f"**Deployed:** {VERSION_INFO['deployment_time'][:19]}"
        )
        await update.message.reply_text(response_text, parse_mode='Markdown')
        logger.info(f"Sent version info to user {update.effective_user.id if update.effective_user else 'unknown'}")
    except Exception as e:
        logger.error(f"Error in version_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error retrieving version information.")

# Admin command handlers
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command - show admin panel for admin users."""
    user_id = update.effective_user.id
    
    if not is_user_admin(user_id):
        await update.message.reply_text("❌ Access denied. This command is only available for administrators.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users")],
        [InlineKeyboardButton("🔧 Admin Settings", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        "🔧 **Admin Panel**\n\n"
        "Welcome to the admin panel. Use the buttons below to access admin features:\n\n"
        "• **Bot Statistics**: View user counts, reminders, and system metrics\n"
        "• **User Management**: Manage users and admin permissions\n"
        "• **Admin Settings**: Configure admin notifications and settings"
    )
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def set_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setadmin command - set admin status for a user."""
    user_id = update.effective_user.id
    
    # Check if current user is admin
    if not is_user_admin(user_id):
        await update.message.reply_text("❌ Access denied. Only administrators can use this command.")
        return
    
    # Parse command arguments
    if not context.args:
        await update.message.reply_text(
            "Usage: `/setadmin <telegram_id> <true/false>`\n\n"
            "Example: `/setadmin 123456789 true` - Make user 123456789 an admin\n"
            "Example: `/setadmin 123456789 false` - Remove admin status from user 123456789",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        admin_status = context.args[1].lower() in ['true', '1', 'yes', 'on']
        
        # Prevent self-demotion
        if target_user_id == user_id and not admin_status:
            await update.message.reply_text("❌ You cannot remove your own admin status.")
            return
        
        success = set_user_admin(target_user_id, admin_status)
        
        if success:
            status_text = "granted" if admin_status else "revoked"
            await update.message.reply_text(
                f"✅ Admin status {status_text} for user `{target_user_id}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to update admin status. User may not exist.")
            
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid Telegram user ID.")
    except Exception as e:
        logger.error(f"Error in set_admin_command: {e}")
        await update.message.reply_text("❌ An error occurred while updating admin status.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - show bot statistics for admin users."""
    user_id = update.effective_user.id
    
    if not is_user_admin(user_id):
        await update.message.reply_text("❌ Access denied. This command is only available for administrators.")
        return
    
    try:
        stats = get_user_stats()
        
        message = (
            "📊 **Bot Statistics**\n\n"
            f"👥 **Users:**\n"
            f"• Total Users: {stats.get('total_users', 0)}\n"
            f"• Premium Users: {stats.get('premium_users', 0)}\n"
            f"• Free Users: {stats.get('free_users', 0)}\n"
            f"• Recent Registrations (24h): {stats.get('recent_registrations', 0)}\n\n"
            f"📝 **Reminders:**\n"
            f"• Active Reminders: {stats.get('total_reminders', 0)}\n\n"
            f"📈 **System Status:**\n"
            f"• Bot Status: ✅ Online\n"
            f"• Database: ✅ Connected\n"
            f"• Admin Mode: ✅ Active"
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stats_command: {e}")
        await update.message.reply_text("❌ An error occurred while retrieving statistics.")

def build_application() -> Application:
    global _application_instance
    init_db()
    # Build application with increased timeout settings to handle network delays
    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .read_timeout(30)  # Increase read timeout to 30 seconds
        .write_timeout(30)  # Increase write timeout to 30 seconds
        .connect_timeout(30)  # Increase connect timeout to 30 seconds
        .pool_timeout(30)  # Increase pool timeout to 30 seconds
        .build()
    )
    _application_instance = application
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("pay", payment_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("stripe_webhook", handle_stripe_webhook))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler(["version", "v"], version_command))
    # Admin commands
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("setadmin", set_admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(CallbackQueryHandler(button_callback))
    async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Received update: {update}")
    application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=100)
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    application.add_error_handler(error_handler)
    job_queue = application.job_queue
    job_queue.run_repeating(check_and_send_reminders, interval=60, first=10)
    logger.info("Background reminder checker job scheduled (runs every 60 seconds)")
    return application