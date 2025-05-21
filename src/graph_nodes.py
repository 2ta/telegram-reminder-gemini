import logging
from typing import Dict, Any, Optional
import json
import google.generativeai as genai
import datetime
import pytz
import jdatetime
import urllib.parse
import uuid 
from sqlalchemy import func, or_

# Import our Persian formatting utilities
from src.persian_utils import to_persian_numerals, get_persian_day_name, get_persian_month_name, format_jalali_date

from src.graph_state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END
from langchain_core.messages import AIMessage
from config.config import settings, MSG_WELCOME, MSG_REMINDER_SET
from src.datetime_utils import parse_persian_datetime_to_utc, resolve_persian_date_phrase_to_range
from src.models import Reminder, User, SubscriptionTier
from src.database import get_db
from sqlalchemy.orm import Session

# Global cache for pending reminder details before confirmation
PENDING_REMINDER_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger(__name__)

async def entry_node(state: AgentState) -> Dict[str, Any]:
    """Node that processes the initial input and determines message type."""
    logger.info(f"Graph: Entered entry_node for user {state.get('user_id')}")
    current_input = state.get("input_text", "")
    message_type = state.get("message_type", "unknown")
    logger.info(f"Input: '{current_input}', Type: {message_type}")
    return {"current_node_name": "entry_node", "user_telegram_details": state.get("user_telegram_details")}

async def load_user_profile_node(state: AgentState) -> Dict[str, Any]:
    """Loads user profile from DB and calculates reminder limits/counts."""
    user_id = state.get("user_id")
    if not user_id:
        logger.error("Cannot load user profile: user_id is missing from state.")
        return {"user_profile": None, "error_message": "User ID missing for profile load.", "current_node_name": "load_user_profile_node"}

    logger.info(f"Graph: Entered load_user_profile_node for user {user_id}")
    db: Session = next(get_db())
    user_db_obj = None # Define user_db_obj to ensure it's available in the scope for creation logic if needed
    try:
        user_db_obj = db.query(User).filter(User.telegram_id == user_id).first()
        
        # User creation/update logic is moved to execute_start_command_node if it's a new user via /start
        # This node now primarily loads existing users or confirms absence for other flows.

        if not user_db_obj:
            logger.info(f"User {user_id} not found in DB during profile load. Will be handled by specific intent nodes (e.g., /start).")
            return {
                "user_profile": None, 
                # No error message here, as it's not an error for this node if user doesn't exist yet.
                # Specific nodes like execute_start_command_node will handle creation.
                "current_node_name": "load_user_profile_node"
            }

        active_reminder_count = db.query(func.count(Reminder.id)).filter(
            Reminder.user_id == user_db_obj.id, # Changed from user_db_id to user_id
            Reminder.is_active == True
        ).scalar() or 0

        # Check if user is premium based on subscription_tier instead of is_premium
        is_premium = user_db_obj.subscription_tier == SubscriptionTier.PREMIUM
        max_reminders = settings.MAX_REMINDERS_PREMIUM_TIER if is_premium else settings.MAX_REMINDERS_FREE_TIER

        user_profile_data = {
            "user_db_id": user_db_obj.id,
            "username": user_db_obj.username,
            "first_name": user_db_obj.first_name,
            "last_name": user_db_obj.last_name,
            "is_premium": is_premium,  # Derived from subscription_tier
            "premium_until": user_db_obj.subscription_expiry.isoformat() if user_db_obj.subscription_expiry else None,
            "language_code": user_db_obj.language_code,
            "reminder_limit": max_reminders,
            "current_reminder_count": active_reminder_count
        }
        logger.info(f"User {user_id} profile loaded: {user_profile_data}")
        return {
            "user_profile": user_profile_data,
            "current_node_name": "load_user_profile_node"
        }
    except Exception as e:
        logger.error(f"Error loading user profile for user {user_id}: {e}", exc_info=True)
        return {
            "user_profile": None, 
            "error_message": f"DB error loading profile: {str(e)}",
            "current_node_name": "load_user_profile_node"
        }
    finally:
        db.close()

async def determine_intent_node(state: AgentState) -> Dict[str, Any]:
    logger.info(f"Graph: Entered determine_intent_node for user {state.get('user_id')}")
    input_text_raw = state.get("input_text")
    input_text = input_text_raw.strip() if input_text_raw else ""
    message_type = state.get("message_type")
    effective_input = input_text # Assuming callback_data is in input_text for callbacks

    # --- START: Handle direct known CREATION confirmation callbacks FIRST ---
    if message_type == "callback_query":
        if effective_input.startswith("confirm_create_reminder:yes:id="):
            logger.info(f"DEBUG: Matched callback for 'confirm_create_reminder:yes:id=': {effective_input}")
            try:
                confirmation_id = effective_input.split("confirm_create_reminder:yes:id=", 1)[1]
                retrieved_data = PENDING_REMINDER_CONFIRMATIONS.pop(confirmation_id, None)
                if retrieved_data:
                    task = retrieved_data.get("task")
                    parsed_dt_utc = retrieved_data.get("parsed_dt_utc")
                    chat_id_from_cache = retrieved_data.get("chat_id")
                    if task and parsed_dt_utc:
                        populated_context = {
                            "collected_task": task,
                            "collected_parsed_datetime_utc": parsed_dt_utc,
                            "chat_id_for_creation": chat_id_from_cache
                        }
                        logger.info(f"Restored context from cache ID {confirmation_id}")
                        return {
                            "current_intent": "intent_create_reminder_confirmed",
                            "extracted_parameters": {},
                            "current_node_name": "determine_intent_node",
                            "reminder_creation_context": populated_context,
                            "pending_confirmation": None
                        }
                    else:
                        logger.error(f"Incomplete data from cache for ID {confirmation_id}")
                        return {"current_intent": "unknown_intent", "response_text": "خطا: اطلاعات تاییدیه ناقص (کش).", "current_node_name": "determine_intent_node"}
                else:
                    logger.warning(f"Confirmation ID {confirmation_id if 'confirmation_id' in locals() else 'UNKNOWN'} not found in cache for {effective_input}")
                    return {"current_intent": "unknown_intent", "response_text": "خطا: تاییدیه منقضی/یافت نشد.", "current_node_name": "determine_intent_node"}
            except Exception as e:
                logger.error(f"Error processing 'yes:id' callback '{effective_input}': {e}", exc_info=True)
                return {"current_intent": "unknown_intent", "response_text": "خطا در پردازش تاییدیه.", "current_node_name": "determine_intent_node"}

        elif effective_input == "confirm_create_reminder:no":
            logger.info(f"DEBUG: Matched callback for 'confirm_create_reminder:no': {effective_input}")
            return {
                "current_intent": "intent_create_reminder_cancelled",
                "response_text": "باشه، تنظیمش نکردم ❌\nفقط کافیه دوباره بگی چی رو کی یادت بندازم 🙂",
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": {},
                "pending_confirmation": None
            }
    # --- END: Handle direct known CREATION confirmation callbacks FIRST ---

    # Get reminder creation context (if any) for clarification flows
    current_reminder_creation_context = state.get("reminder_creation_context") if state.get("reminder_creation_context") is not None else {}
    pending_clarification_type = current_reminder_creation_context.get("pending_clarification_type")
    
    # If API key is missing, can't perform NLU
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Skipping NLU.")
        return {"current_intent": "unknown_intent", "extracted_parameters": {"error_in_nlu": "API key missing"}, "current_node_name": "determine_intent_node"}
    
    # Check for command intents first (before using the LLM)
    if input_text.startswith('/'):
        # Handle specific commands
        if input_text == '/start':
            logger.info(f"Detected /start command from user {state.get('user_id')}")
            return {"current_intent": "intent_start", "current_node_name": "determine_intent_node"}
        elif input_text == '/help':
            logger.info(f"Detected /help command from user {state.get('user_id')}")
            return {"current_intent": "intent_help", "current_node_name": "determine_intent_node"}
        elif input_text == '/reminders' or input_text.startswith('/reminders '):
            logger.info(f"Detected /reminders command from user {state.get('user_id')}")
            return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": 1}, "current_node_name": "determine_intent_node"}
        elif input_text.startswith('/del_'):
            # Format: /del_123 where 123 is the reminder ID
            try:
                reminder_id = int(input_text.split('_')[1])
                logger.info(f"Detected delete reminder command for ID {reminder_id} from user {state.get('user_id')}")
                return {"current_intent": "intent_delete_reminder", "extracted_parameters": {"reminder_id": reminder_id}, "current_node_name": "determine_intent_node"}
            except (IndexError, ValueError) as e:
                logger.warning(f"Invalid delete reminder command: {input_text}, error: {e}")
                return {"current_intent": "unknown_intent", "response_text": "فرمت دستور حذف نامعتبر است. لطفاً از دکمه حذف کنار یادآور استفاده کنید.", "current_node_name": "determine_intent_node"}
    
    # Rule-based NLU for common Persian reminder creation patterns
    reminder_patterns = [
        "یادم بنداز",
        "یادآوری کن",
        "یادم بیار",
        "یادم نره",
        "فراموش نکنم",
        "یادم باشه",
        "یادم میندازی"
    ]
    
    # First check if this is a reminder creation request using pattern matching
    is_reminder_request = False
    for pattern in reminder_patterns:
        if pattern in input_text.lower():
            is_reminder_request = True
            break
    
    # If it looks like a reminder request, extract task and time parameters
    if is_reminder_request:
        logger.info(f"Detected potential reminder creation intent from user {state.get('user_id')}: '{input_text}'")
        
        # Extract date/time patterns (simplified - real implementation would be more sophisticated)
        # For demo purposes, look for common Persian date/time patterns
        task = input_text  # Default to using the whole input as task
        
        # Try to find date components
        date_str = None
        time_str = None
        
        # Simplified date extraction - in a real implementation, this would use regex or more sophisticated parsing
        date_indicators = ["فردا", "امروز", "پس فردا", "هفته آینده", "ماه آینده", "شنبه", "یکشنبه", "دوشنبه", "سه شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
        time_indicators = ["ساعت", "صبح", "ظهر", "عصر", "شب", "بعد از ظهر"]
        
        # Very simplified extraction - in real implementation, this would be more sophisticated
        for indicator in date_indicators:
            if indicator in input_text:
                date_str = indicator
                break
        
        for indicator in time_indicators:
            if indicator in input_text:
                # Try to find time pattern (e.g., ساعت ۴)
                words = input_text.split()
                for i, word in enumerate(words):
                    if word == "ساعت" and i < len(words) - 1:
                        time_str = f"ساعت {words[i+1]}"
                        break
                if not time_str:
                    time_str = indicator
                break
        
        # For task extraction, we'll just pass the full text for now
        # In a real implementation, we would try to isolate just the task portion
        # by removing the date/time portions
        
        logger.info(f"Extracted reminder parameters - date: '{date_str}', time: '{time_str}', task: '{task}'")
        
        return {
            "current_intent": "intent_create_reminder",
            "extracted_parameters": {
                "date": date_str,
                "time": time_str,
                "task": task
            },
            "current_node_name": "determine_intent_node",
            "reminder_creation_context": {
                "collected_date_str": date_str,
                "collected_time_str": time_str,
                "collected_task": task,
                "pending_clarification_type": None  # Will be set by validation node if needed
            }
        }
    
    # If we get here, it's not a known command or reminder pattern
    logger.warning(f"Could not determine intent for: '{input_text}'")
    return {
        "current_intent": "unknown_intent", 
        "extracted_parameters": {"input_was": input_text}, 
        "response_text": f"متاسفانه منظور شما از «{input_text}» را متوجه نشدم. برای راهنمایی /help را ارسال کنید.",
        "current_node_name": "determine_intent_node",
        "reminder_creation_context": current_reminder_creation_context
    }

async def execute_start_command_node(state: AgentState) -> Dict[str, Any]:
    """Handles the /start command logic: create/update user, send welcome message."""
    user_id = state.get("user_id")
    chat_id = state.get("chat_id")
    user_profile = state.get("user_profile") # Loaded by load_user_profile_node
    # user_telegram_details should be populated in AgentState by bot.py for /start command
    user_telegram_details = state.get("user_telegram_details") 

    logger.info(f"Graph: Entered execute_start_command_node for user {user_id}")

    if not user_id or not chat_id: # chat_id is essential for user record and responses
        logger.error(f"execute_start_command_node: Missing user_id ({user_id}) or chat_id ({chat_id}). Cannot proceed.")
        return {"error_message": "Internal error: User or chat identifier missing for start command."}

    db: Session = next(get_db())
    try:
        user_obj = db.query(User).filter(User.telegram_id == user_id).first()

        if not user_obj:
            logger.info(f"User {user_id} not found. Creating new user.")
            if not user_telegram_details: # These details are important for new user creation
                logger.warning(f"execute_start_command_node: user_telegram_details missing for new user {user_id}. User record will be incomplete.")
                # Fallback to empty strings if details are missing, though ideally they should be passed.
                user_telegram_details = {"username": None, "first_name": "User", "last_name": None, "language_code": "en"}
            
            user_obj = User(
                telegram_id=user_id,
                username=user_telegram_details.get("username"),
                first_name=user_telegram_details.get("first_name"),
                last_name=user_telegram_details.get("last_name"),
                language_code=user_telegram_details.get("language_code")
            )
            db.add(user_obj)
            db.commit()
            db.refresh(user_obj) # To get the new user_obj.id if needed immediately
            logger.info(f"New user {user_id} created successfully.")
            # Update user_profile in state as it was None before
            user_profile = {
                "user_db_id": user_obj.id,
                "username": user_obj.username,
                "first_name": user_obj.first_name,
                "last_name": user_obj.last_name,
                "is_premium": user_obj.subscription_tier == SubscriptionTier.PREMIUM,  # Derived from subscription_tier
                "premium_until": None,
                "language_code": user_obj.language_code,
                "reminder_limit": settings.MAX_REMINDERS_FREE_TIER,
                "current_reminder_count": 0
            }
        else:
            logger.info(f"User {user_id} found. Updating details if necessary.")
            # Update chat_id and other details if they might change
            needs_commit = False
            if user_telegram_details:
                if user_obj.username != user_telegram_details.get("username"):
                    user_obj.username = user_telegram_details.get("username")
                    needs_commit = True
                if user_obj.first_name != user_telegram_details.get("first_name"):
                    user_obj.first_name = user_telegram_details.get("first_name")
                    needs_commit = True
                if user_obj.last_name != user_telegram_details.get("last_name"):
                    user_obj.last_name = user_telegram_details.get("last_name")
                    needs_commit = True
                if user_obj.language_code != user_telegram_details.get("language_code"):
                    user_obj.language_code = user_telegram_details.get("language_code")
                    needs_commit = True
            if needs_commit:
                db.commit()
                logger.info(f"User {user_id} details updated.")
        
        welcome_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [{"text": "یادآورهای من 📝", "callback_data": "view_reminders:page:1"}, {"text": "راهنما ❓", "callback_data": "trigger_help_intent"}],
                [{"text": "تهیه اشتراک ویژه 👑", "callback_data": "show_subscription_options"}]
            ]
        }
        logger.info(f"Created welcome keyboard markup: {welcome_keyboard}")

        return {
            "response_text": MSG_WELCOME,
            "response_keyboard_markup": welcome_keyboard,
            "user_profile": user_profile, # Return updated/created user_profile
            "current_node_name": "execute_start_command_node"
        }

    except Exception as e:
        logger.error(f"Error in execute_start_command_node for user {user_id}: {e}", exc_info=True)
        db.rollback()
        return {"error_message": f"DB error during start command: {str(e)}"}
    finally:
        db.close()

async def process_datetime_node(state: AgentState) -> Dict[str, Any]:
    """Node to parse date and time strings from extracted_parameters OR reminder_creation_context into a UTC datetime object."""
    logger.info(f"Graph: Entered process_datetime_node for user {state.get('user_id')}")
    current_intent = state.get("current_intent")
    # Prioritize context if available, then fallback to extracted_params (e.g., for initial NLU run)
    reminder_ctx = state.get("reminder_creation_context", {})
    extracted_params = state.get("extracted_parameters", {})
    
    parsed_dt_utc: Optional[datetime.datetime] = None
    
    # --- Populate context from extracted_params if not already there ---
    # This node is a good point to consolidate initial NLU results into the context
    if not reminder_ctx.get("collected_task") and extracted_params.get("task"):
        reminder_ctx["collected_task"] = extracted_params["task"]
        logger.info(f"Task '{extracted_params['task']}' collected from NLU into context.")
    
    # Similarly for date/time strings, though NLU might not always provide them initially
    if not reminder_ctx.get("collected_date_str") and extracted_params.get("date"):
        reminder_ctx["collected_date_str"] = extracted_params["date"]
    if not reminder_ctx.get("collected_time_str") and extracted_params.get("time"):
        reminder_ctx["collected_time_str"] = extracted_params["time"]
    # --- End context population ---

    # Fields for parsing (now reliably from context or populated from NLU)
    date_str = reminder_ctx.get("collected_date_str") # or extracted_params.get("date") <- no longer needed here
    time_str = reminder_ctx.get("collected_time_str") # or extracted_params.get("time") <- no longer needed here
    
    # am_pm_choice is not used by the current parser, so no need to pull it from extracted_params here.
    # It was removed from the parse_persian_datetime_to_utc call.

    # Only attempt parsing if intent is reminder-related and parameters are present
    if current_intent == "intent_create_reminder": # Or if it's an edit flow later
        if date_str or time_str:
            logger.info(f"Attempting to parse date='{date_str}', time='{time_str}' for intent '{current_intent}'") # Removed am_pm from log
            try:
                # Pass am_pm_choice to the parser if available - REMOVED, parser handles periods internally
                parsed_dt_utc = parse_persian_datetime_to_utc(date_str, time_str) # Removed am_pm_choice
                if parsed_dt_utc:
                    logger.info(f"Successfully parsed datetime to UTC: {parsed_dt_utc}")
                    # Store in context for subsequent nodes
                    reminder_ctx["collected_parsed_datetime_utc"] = parsed_dt_utc
                    # Clear am_pm_choice from context once used for parsing (or if it was never meant for this parser)
                    if "collected_am_pm_choice" in reminder_ctx:
                        del reminder_ctx["collected_am_pm_choice"]
                    if "ambiguous_time_details" in reminder_ctx: # Clear ambiguity once resolved
                         del reminder_ctx["ambiguous_time_details"]
                else:
                    logger.warning(f"Failed to parse date/time from strings: date='{date_str}', time='{time_str}'")
                    # If parsing fails, ensure collected_parsed_datetime_utc is None or removed
                    reminder_ctx["collected_parsed_datetime_utc"] = None
            except Exception as e:
                logger.error(f"Error during date/time parsing: {e}", exc_info=True)
                reminder_ctx["collected_parsed_datetime_utc"] = None
        else:
            logger.info(f"No date/time strings found in context/params for intent '{current_intent}'")
            reminder_ctx["collected_parsed_datetime_utc"] = None # Ensure it's None
    else:
        logger.info(f"Skipping datetime parsing for intent '{current_intent}'.")

    # Return the direct parsed_dt_utc for immediate use by next node, but also ensure context is updated
    return {
        "parsed_datetime_utc": reminder_ctx.get("collected_parsed_datetime_utc"), # Use the one from context
        "current_node_name": "process_datetime_node",
        "reminder_creation_context": reminder_ctx, # Pass updated context
        "validated_task": state.get("validated_task"), # Pass through for now
        "reminder_creation_status": state.get("reminder_creation_status") # Pass through
    }

async def validate_and_clarify_reminder_node(state: AgentState) -> Dict[str, Any]:
    """
    Validates collected reminder details (task, datetime from context).
    If details are missing or ambiguous, sets up for clarification.
    If details are complete and valid, sets status for confirmation.
    Also checks tier limits before proceeding to confirmation.
    """
    user_id = state.get("user_id")
    logger.info(f"Graph: Entered validate_and_clarify_reminder_node for user {user_id}")
    
    reminder_ctx = state.get("reminder_creation_context") if state.get("reminder_creation_context") is not None else {}
    user_profile = state.get("user_profile") # Can be None

    collected_task = reminder_ctx.get("collected_task")
    collected_parsed_dt_utc = reminder_ctx.get("collected_parsed_datetime_utc")
    
    # Default to free tier limits if profile is not loaded yet (e.g., new user)
    current_reminder_count = 0
    reminder_limit = settings.MAX_REMINDERS_FREE_TIER
    is_premium = False
    tier_name = "رایگان" # Default tier name for messaging

    if user_profile: # If profile exists, use its values
        current_reminder_count = user_profile.get("current_reminder_count", 0)
        reminder_limit = user_profile.get("reminder_limit", settings.MAX_REMINDERS_FREE_TIER)
        is_premium = user_profile.get("is_premium", False)
        tier_name = "ویژه" if is_premium else "رایگان"
    else:
        logger.info(f"User profile not available for user {user_id} in validation node. Assuming free tier limits.")

    new_reminder_creation_status: Optional[str] = None
    pending_clarification_type: Optional[str] = None
    clarification_question_text: Optional[str] = None
    clarification_keyboard_markup: Optional[Dict[str, Any]] = None

    # --- 1. Check Reminder Limits ---
    if not settings.IGNORE_REMINDER_LIMITS and current_reminder_count >= reminder_limit:
        logger.warning(f"User {user_id} (Premium: {is_premium}) has reached reminder limit. Count: {current_reminder_count}, Limit: {reminder_limit}")
        
        limit_message_template = settings.MSG_REMINDER_LIMIT_REACHED_WITH_BUTTON
        if is_premium:
            limit_message_template = settings.MSG_REMINDER_LIMIT_REACHED_PREMIUM
        # For free users, MSG_REMINDER_LIMIT_REACHED_WITH_BUTTON is suitable directly
        # as it implies an upgrade path.
        # If a specific MSG_REMINDER_LIMIT_REACHED_FREE existed and was different, we might choose it here.

        response_text = limit_message_template.format(
            limit=to_persian_numerals(str(reminder_limit)), 
            tier_name=tier_name
        )
        
        limit_exceeded_keyboard = None
        if not is_premium: # Show subscription options button only for non-premium users
            limit_exceeded_keyboard = {
                "type": "InlineKeyboardMarkup",
                "inline_keyboard": [
                    [{"text": "تهیه اشتراک ویژه 👑", "callback_data": "show_subscription_options"}]
                ]
            }

        return {
            "reminder_creation_status": "error_limit_exceeded",
            "response_text": response_text,
            "response_keyboard_markup": limit_exceeded_keyboard,
            "current_node_name": "validate_and_clarify_reminder_node",
            "pending_confirmation": None, # No confirmation pending
            "reminder_creation_context": reminder_ctx # Pass context through
        }

    # --- 2. Validate Task ---
    if not collected_task:
        logger.info(f"Validation failed for user {user_id}: Task is missing.")
        pending_clarification_type = "task"
        clarification_question_text = "لطفاً بفرمایید برای چه کاری می‌خواهید یادآور تنظیم کنید؟"
        new_reminder_creation_status = "clarification_needed_task"
    # 3. Validate Datetime
    elif not collected_parsed_dt_utc:
        logger.info(f"Validation failed for user {user_id}, task '{collected_task}': Datetime is missing or unparseable.")
        pending_clarification_type = "datetime"
        clarification_question_text = f"برای یادآور «{collected_task}» چه تاریخ و ساعتی مدنظرتان است؟"
        new_reminder_creation_status = "clarification_needed_datetime"
        # Potentially check if ambiguous_time_details is set from a previous AM/PM NLU attempt that didn't parse
        # This would primarily be if parse_persian_datetime_to_utc itself could signal ambiguity.
        # For now, relying on separate AM/PM clarification if `collected_am_pm_choice` was needed and not provided to `parse_persian_datetime_to_utc`.
        # If `collected_am_pm_choice` is present in `reminder_ctx` but parsing still failed, it means the date/time itself was bad.

    # (Future AM/PM specific clarification check - assuming parse_persian_datetime_to_utc handles am_pm_choice or returns None if it's ambiguous and choice is missing)
    # For instance, if parse_persian_datetime_to_utc returned a specific error or flag for AM/PM:
    # elif reminder_ctx.get("datetime_parse_requires_ampm_clarification"):
    #     logger.info(f"Validation for user {user_id}, task '{collected_task}': AM/PM clarification needed.")
    #     pending_clarification_type = "am_pm"
    #     ambiguous_hour = reminder_ctx.get("ambiguous_time_details", {}).get("hour", "ساعت مورد نظر")
    #     clarification_question_text = f"ساعت {ambiguous_hour} صبح است یا بعد از ظهر؟"
    #     clarification_keyboard_markup = {
    #         "type": "InlineKeyboardMarkup",
    #         "inline_keyboard": [
    #             [{"text": "☀️ صبح (AM)", "callback_data": "clarify_am_pm:am"}, {"text": "🌙 بعد از ظهر (PM)", "callback_data": "clarify_am_pm:pm"}]
    #         ]}
    #     new_reminder_creation_status = "clarification_needed_am_pm"
    #     # Ensure determine_intent_node handles "clarify_am_pm:am/pm" callbacks and sets "collected_am_pm_choice"

    else:
        logger.info(f"Validation successful for user {user_id}: Task='{collected_task}', Datetime='{collected_parsed_dt_utc}'. Ready for confirmation.")
        new_reminder_creation_status = "ready_for_confirmation"


    reminder_ctx["pending_clarification_type"] = pending_clarification_type
    reminder_ctx["clarification_question_text"] = clarification_question_text
    reminder_ctx["clarification_keyboard_markup"] = clarification_keyboard_markup
    reminder_ctx["status"] = new_reminder_creation_status # Update status in context

    logger.info(f"validate_and_clarify_reminder_node returning with reminder_creation_context.status: '{new_reminder_creation_status}'")
    return {
        "reminder_creation_context": reminder_ctx, # The status is also inside this dict
        "reminder_creation_status": new_reminder_creation_status, # Explicitly return status as a separate field
        "current_node_name": "validate_and_clarify_reminder_node"
    }

async def confirm_reminder_details_node(state: AgentState) -> Dict[str, Any]:
    """Node to confirm the reminder details with the user."""
    user_id = state.get("user_id")
    logger.info(f"Graph: Entered confirm_reminder_details_node for user {user_id}")
    
    reminder_ctx = state.get("reminder_creation_context", {})
    
    try:
        task = reminder_ctx.get("collected_task", "")
        parsed_dt_utc = reminder_ctx.get("collected_parsed_datetime_utc")
        
        if not task or not parsed_dt_utc:
            logger.error(f"Error in confirm_reminder_details_node: Missing task or datetime for user {user_id}")
            return {
                "response_text": "مشکلی در پردازش اطلاعات یادآور رخ داده است. لطفاً دوباره تلاش کنید.",
                "current_node_name": "confirm_reminder_details_node",
                "pending_confirmation": None
            }
            
        tehran_tz = pytz.timezone("Asia/Tehran")
        dt_tehran = parsed_dt_utc.astimezone(tehran_tz)
        
        # Format to Jalali date and time with Persian numerals
        jalali_date = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
        
        # Helper to convert English digits to Persian
        def to_persian_numerals(text: str) -> str:
            persian_numerals_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
            return str(text).translate(persian_numerals_map) # Ensure input is string

        # Format date and time parts using our Persian utilities
        persian_day_name = get_persian_day_name(jalali_date)
        persian_month_name = get_persian_month_name(jalali_date)
        
        persian_day_num = to_persian_numerals(str(jalali_date.day))
        persian_year_num = to_persian_numerals(str(jalali_date.year))
        persian_time_str = to_persian_numerals(dt_tehran.strftime("%H:%M"))

        formatted_datetime_persian = f"{persian_day_name} {persian_day_num} {persian_month_name} {persian_year_num}، ساعت {persian_time_str}"

        # Encode task and UTC datetime string into callback_data for stateless retrieval
        # Ensure task is URL-encoded if it can contain special characters for callback_data
        encoded_task = urllib.parse.quote(task)
        dt_utc_iso = parsed_dt_utc.isoformat() # Produces string like "YYYY-MM-DDTHH:MM:SS+00:00" or with Z

        # Store task and parsed_dt_utc in cache, use ID in callback
        confirmation_id = uuid.uuid4().hex
        # Ensure chat_id is available in the state for storing
        chat_id_for_cache = state.get("chat_id", state.get("user_id")) # Fallback to user_id if chat_id specifically isn't there

        PENDING_REMINDER_CONFIRMATIONS[confirmation_id] = {
            "task": task, 
            "parsed_dt_utc": parsed_dt_utc,
            "chat_id": chat_id_for_cache 
        }
        logger.info(f"Stored pending confirmation details for ID {confirmation_id}. Cache size: {len(PENDING_REMINDER_CONFIRMATIONS)}")
        # Schedule a cleanup for this entry after some time to prevent orphan entries if callback never comes
        # This is more advanced; for now, we rely on retrieval for cleanup.

        callback_data_yes = f"confirm_create_reminder:yes:id={confirmation_id}"
        callback_data_no = "confirm_create_reminder:no" 

        confirmation_message = (
            f"یادآور زیر رو تنظیم کنم؟ 👇\n\n"
            f"📝 متن: {task}\n"
            f"⏰ زمان: {formatted_datetime_persian}\n\n"
            f"اگه درسته، روی «تنظیم کن» بزن\n"
            f"اگه نیاز به تغییر داره، روی «رد» بزن و یادآور جدید رو دوباره بفرست 🙂"
        )
        
        confirmation_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [
                    {"text": "تنظیم کن ✅", "callback_data": callback_data_yes},
                    {"text": "رد ❌", "callback_data": callback_data_no}
                ]
            ]
        }
        logger.info(f"Prepared confirmation for user {state.get('user_id')}: Task='{task}', DateTime='{formatted_datetime_persian}'")
        logger.debug(f"confirm_reminder_details_node returning reminder_ctx: {reminder_ctx}") # ADDED LOGGING

        return {
            "response_text": confirmation_message,
            "response_keyboard_markup": confirmation_keyboard,
            "pending_confirmation": "create_reminder", # Set flag that we are awaiting confirmation
            "current_node_name": "confirm_reminder_details_node",
            "reminder_creation_context": reminder_ctx # Pass context through
        }

    except Exception as e:
        logger.error(f"Error in confirm_reminder_details_node: {e}", exc_info=True)
        return {
            "response_text": "خطایی در آماده‌سازی پیام تایید رخ داد. لطفاً دوباره تلاش کنید.",
            "current_node_name": "confirm_reminder_details_node",
            "pending_confirmation": None,
            "reminder_creation_context": reminder_ctx
        }

async def create_reminder_node(state: AgentState) -> Dict[str, Any]:
    """Node to create the reminder in the database after user confirmation."""
    user_id = state.get("user_id")
    # Get chat_id primarily from reminder_creation_context (set by determine_intent for callbacks),
    # then from root state as a fallback.
    reminder_ctx = state.get("reminder_creation_context", {})
    chat_id_for_reminder = reminder_ctx.get("chat_id_for_creation", state.get("chat_id"))
    
    logger.info(f"Graph: Entered create_reminder_node for user {user_id}. Effective chat_id for reminder: {chat_id_for_reminder}")
    # reminder_ctx = state.get("reminder_creation_context", {}) # Already got it
    user_profile = state.get("user_profile")
    logger.debug(f"create_reminder_node received reminder_ctx: {reminder_ctx}")
    
    reminder_ctx = state.get("reminder_creation_context", {})
    user_profile = state.get("user_profile") # This should be loaded
    logger.debug(f"create_reminder_node received reminder_ctx: {reminder_ctx}") # ADDED LOGGING

    task = reminder_ctx.get("collected_task")
    # Ensure collected_parsed_datetime_utc is a datetime object
    parsed_dt_utc_from_ctx = reminder_ctx.get("collected_parsed_datetime_utc")
    logger.debug(f"create_reminder_node: task='{task}', parsed_dt_utc_from_ctx='{parsed_dt_utc_from_ctx}' (type: {type(parsed_dt_utc_from_ctx)})") # ADDED LOGGING

    if not isinstance(parsed_dt_utc_from_ctx, datetime.datetime):
        if isinstance(parsed_dt_utc_from_ctx, str):
            try:
                # Attempt to parse from ISO format if it's a string (e.g., from reloaded state)
                parsed_dt_utc = datetime.datetime.fromisoformat(parsed_dt_utc_from_ctx.replace('Z', '+00:00'))
            except ValueError:
                logger.error(f"Could not parse datetime string from context: {parsed_dt_utc_from_ctx}")
                return {
                    "reminder_creation_status": "error_invalid_datetime_format_in_context",
                    "response_text": "خطا: فرمت تاریخ و زمان ذخیره شده نامعتبر است.",
                    "current_node_name": "create_reminder_node",
                    "reminder_creation_context": reminder_ctx,
                    "pending_confirmation": None
                }
        else:
            logger.error(f"Invalid datetime in context for user {user_id}. Task: {task}, DT: {parsed_dt_utc_from_ctx} (type: {type(parsed_dt_utc_from_ctx)})")
            return {
                "reminder_creation_status": "error_missing_details",
                "response_text": "خطا: اطلاعات یادآور ناقص یا نامعتبر است.",
                "current_node_name": "create_reminder_node",
                "reminder_creation_context": reminder_ctx,
                "pending_confirmation": None
            }
    else:
        parsed_dt_utc = parsed_dt_utc_from_ctx


    if not task or not parsed_dt_utc:
        logger.error(f"Missing task or datetime for user {user_id} in create_reminder_node. Task: {task}, DT: {parsed_dt_utc}")
        return {
            "reminder_creation_status": "error_missing_details",
            "response_text": "خطا: اطلاعات یادآور برای ایجاد ناقص است.",
            "current_node_name": "create_reminder_node",
            "reminder_creation_context": reminder_ctx, # Pass context
            "pending_confirmation": None
        }

    if not user_profile or not user_profile.get("user_db_id"):
        logger.warning(f"User profile or user_db_id missing for {user_id}. Attempting to load/re-load.")
        db_temp: Session = next(get_db())
        try:
            user_db_obj_temp = db_temp.query(User).filter(User.telegram_id == user_id).first()
            if user_db_obj_temp:
                user_profile = { # Reconstruct a minimal profile part
                    "user_db_id": user_db_obj_temp.id,
                    # Add other necessary fields if create_reminder logic depends on them
                }
                logger.info(f"Successfully re-loaded user_db_id: {user_db_obj_temp.id} for user {user_id}")
            else:
                logger.error(f"Failed to find user {user_id} in DB during create_reminder_node.")
                return {"reminder_creation_status": "error_user_not_found", "response_text": "خطا: کاربر برای ایجاد یادآور یافت نشد.", "current_node_name": "create_reminder_node", "pending_confirmation": None}
        finally:
            db_temp.close()
    
    user_db_id = user_profile.get("user_db_id")
    if not user_db_id: # Should not happen if above logic works
        logger.error(f"Critical: user_db_id still missing for user {user_id} before DB operation.")
        return {"reminder_creation_status": "error_internal_user_id_missing", "response_text": "خطای داخلی: شناسه کاربر موجود نیست.", "current_node_name": "create_reminder_node", "pending_confirmation": None}


    # Reminder Limit Check (re-check here as a safeguard, though validate_and_clarify should handle it)
    # This requires a full user_profile, so if it was minimally reloaded, this check might be less effective
    # or might need to fetch counts again. For simplicity, we assume validate_and_clarify_node did its job.

    db: Session = next(get_db())
    try:
        # Convert UTC datetime to Tehran timezone and create Jalali date strings
        tehran_tz = pytz.timezone("Asia/Tehran") 
        dt_tehran = parsed_dt_utc.astimezone(tehran_tz)
        jalali_date = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
        
        # Format for database storage
        jalali_date_str = jalali_date.strftime("%Y-%m-%d")
        time_str = dt_tehran.strftime("%H:%M")
        
        new_reminder = Reminder(
            user_id=user_db_id,  # Use the user's actual DB ID
            task=task,
            due_datetime_utc=parsed_dt_utc,  # Use the correct field name from the model
            jalali_date_str=jalali_date_str,  # Add jalali_date_str
            time_str=time_str,  # Add time_str
            is_active=True
        )
        db.add(new_reminder)
        db.commit()
        db.refresh(new_reminder)
        logger.info(f"Reminder created successfully for user_db_id {user_db_id} (Telegram user {user_id}), task: '{task}', due_datetime_utc: {parsed_dt_utc}")

        # Update user_profile's reminder count if profile is fully available
        if user_profile and "current_reminder_count" in user_profile:
            user_profile["current_reminder_count"] += 1
        
        # Format for MSG_REMINDER_SET using Persian numerals
        tehran_tz = pytz.timezone("Asia/Tehran")
        dt_tehran = parsed_dt_utc.astimezone(tehran_tz)
        jalali_date_obj = jdatetime.datetime.fromgregorian(datetime=dt_tehran)

        def to_persian_numerals(text: str) -> str:
            persian_numerals_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
            return str(text).translate(persian_numerals_map) # Ensure input is string

        # The old MSG_REMINDER_SET is no longer used here directly.
        # New success message:
        response_message = (
            "تمومه! 🎉\n"
            "یادآورت با موفقیت تنظیم شد و سر وقت بهت خبر می‌دم 🔔"
        )

        # For logging, we might still want the detailed Persian date/time
        # Use our Persian utilities
        persian_day_name = get_persian_day_name(jalali_date_obj)
        persian_month_name = get_persian_month_name(jalali_date_obj)
        
        persian_day_num = to_persian_numerals(str(jalali_date_obj.day))
        persian_year_num = to_persian_numerals(str(jalali_date_obj.year))
        persian_time_str = to_persian_numerals(dt_tehran.strftime("%H:%M"))
        formatted_datetime_for_log = f"{persian_day_name} {persian_day_num} {persian_month_name} {persian_year_num}، ساعت {persian_time_str}"
        logger.info(f"Reminder successfully set. Task: {task}, Persian Time: {formatted_datetime_for_log}")

        return {
            "reminder_creation_status": "success",
            "response_text": response_message,
            "user_profile": user_profile, # Pass updated profile
            "current_node_name": "create_reminder_node",
            "reminder_creation_context": {}, # Clear context after successful creation
            "pending_confirmation": None # Clear pending confirmation
        }
    except Exception as e:
        logger.error(f"Error creating reminder in DB for user {user_id}: {e}", exc_info=True)
        db.rollback()
        return {
            "reminder_creation_status": "error_db_create",
            "response_text": "متاسفانه در ایجاد یادآور شما در پایگاه داده خطایی رخ داد.",
            "current_node_name": "create_reminder_node",
            "reminder_creation_context": reminder_ctx, # Keep context for potential retry/debug
            "pending_confirmation": None
        }
    finally:
        db.close()

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Handles the determined intent, e.g., fetching reminders, preparing help message."""
    current_intent = state.get("current_intent")
    user_id = state.get("user_id")
    user_profile = state.get("user_profile")
    extracted_parameters = state.get("extracted_parameters", {})
    # Get status from create_reminder_node if available
    reminder_creation_status = state.get("reminder_creation_status") 
    logger.info(f"Graph: Entered handle_intent_node for user {user_id}, intent: {current_intent}, params: {extracted_parameters}, status: {reminder_creation_status}")

    # Initialize with default, but prioritize pre-set text for specific intents/statuses.
    response_text = "کاری که از من خواستید را متوجه نشدم. لطفاً واضح‌تر بگویید یا از دستور /help استفاده کنید."
    response_keyboard_markup = state.get("response_keyboard_markup") # Preserve from previous node if any
    
    updated_state_dict = {"current_node_name": "handle_intent_node"}

    def to_persian_numerals(text: str) -> str:
        persian_numerals_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        return str(text).translate(persian_numerals_map) # Ensure input is string

    # Handle intents that might have a pre-set response_text from upstream nodes
    if current_intent == "intent_create_reminder_confirmed" and reminder_creation_status == "success":
        pre_set_text = state.get("response_text") # This is the "تمومه! 🎉..." from create_reminder_node
        if pre_set_text:
            response_text = pre_set_text
            response_keyboard_markup = None # Explicitly no keyboard for this success message
            logger.info(f"Using pre-set success response for confirmed reminder: '{response_text}'")
        else:
            # Fallback if text wasn't set by create_reminder_node, though it should be.
            response_text = "یادآور با موفقیت ایجاد شد." 
            response_keyboard_markup = None
            
    elif current_intent == "intent_create_reminder_cancelled":
        pre_set_text = state.get("response_text") # This is the "باشه، تنظیمش نکردم..." from determine_intent_node
        if pre_set_text:
            response_text = pre_set_text
            response_keyboard_markup = None # Explicitly no keyboard for this message
            logger.info(f"Using pre-set response for intent_create_reminder_cancelled: '{response_text}'")
        else:
            # Fallback if text wasn't set, though it should be by determine_intent_node
            response_text = "یادآور لغو شد." 
            response_keyboard_markup = None
            
    elif current_intent == "intent_create_reminder":
        # This intent implies the start of a creation process, not a confirmation/cancellation outcome handled above.
        response_text = "لطفاً بگویید چه چیزی را و برای کی می‌خواهید یادآوری کنم."

    elif current_intent == "intent_view_reminders":
        if not user_profile or not user_profile.get("user_db_id"):
            logger.warning(f"User profile or user_db_id missing for viewing reminders (user: {user_id}).")
            response_text = "خطا: شناسه کاربری برای مشاهده یادآورها یافت نشد یا پروفایل بارگذاری نشده است."
        else:
            user_db_id = user_profile["user_db_id"]
            page = extracted_parameters.get("page", 1)
            if not isinstance(page, int) or page < 1:
                page = 1
            
            active_filters = state.get("active_reminder_filters", {})
            filter_description_list = []

            db: Session = next(get_db())
            try:
                query = db.query(Reminder).filter(Reminder.user_id == user_db_id, Reminder.is_active == True)
                
                if active_filters.get("by_task_keyword"):
                    keyword = active_filters["by_task_keyword"]
                    query = query.filter(Reminder.task.ilike(f"%{keyword}%"))
                    filter_description_list.append(f"حاوی کلمه «{keyword}» در متن")
                
                if active_filters.get("by_date_exact"):
                    exact_date = active_filters["by_date_exact"]
                    if isinstance(exact_date, str):
                        exact_date = datetime.datetime.fromisoformat(exact_date).date()
                    query = query.filter(func.date(Reminder.due_datetime_utc) == exact_date)
                    jalali_exact_date = jdatetime.date.fromgregorian(date=exact_date)
                    filter_description_list.append(f"در تاریخ {to_persian_numerals(jalali_exact_date.strftime('%Y/%m/%d'))}")
                
                elif active_filters.get("by_date_range_start") and active_filters.get("by_date_range_end"):
                    start_date_utc = active_filters["by_date_range_start"]
                    end_date_utc = active_filters["by_date_range_end"]
                    query = query.filter(Reminder.due_datetime_utc.between(start_date_utc, end_date_utc))
                    tehran_tz = pytz.timezone("Asia/Tehran")
                    start_local = pytz.utc.localize(start_date_utc).astimezone(tehran_tz)
                    end_local = pytz.utc.localize(end_date_utc).astimezone(tehran_tz)
                    jalali_start = jdatetime.datetime.fromgregorian(datetime=start_local)
                    jalali_end = jdatetime.datetime.fromgregorian(datetime=end_local)
                    filter_description_list.append(f"بین {to_persian_numerals(jalali_start.strftime('%Y/%m/%d'))} و {to_persian_numerals(jalali_end.strftime('%Y/%m/%d'))}")

                query = query.order_by(Reminder.due_datetime_utc.asc())
                
                total_reminders = query.count()
                reminders_per_page = settings.REMINDERS_PER_PAGE
                offset = (page - 1) * reminders_per_page
                reminders_page = query.limit(reminders_per_page).offset(offset).all()

                if not reminders_page and page == 1 and not active_filters:
                    response_text = "شما در حال حاضر هیچ یادآور فعالی ندارید."
                elif not reminders_page and active_filters:
                    response_text = MSG_LIST_EMPTY_WITH_FILTERS
                elif not reminders_page and page > 1:
                    response_text = f"صفحه {to_persian_numerals(str(page))} خالی است. به نظر می‌رسد تمام یادآورها را مشاهده کرده‌اید."
                else: # Corrected else alignment
                    header = MSG_LIST_HEADER_WITH_FILTERS if active_filters else "یادآورهای فعال شما:"
                    filter_summary = "" 
                    if filter_description_list:
                        filter_summary = f"\n🔍 فیلترها: { '، '.join(filter_description_list)}"
                    
                    response_lines = [f"{header}{filter_summary}\n"]
                    tehran_tz = pytz.timezone("Asia/Tehran")
                    for i, reminder in enumerate(reminders_page):
                        dt_tehran = reminder.due_datetime_utc.astimezone(tehran_tz)
                        jalali_date = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
                        
                        persian_day_name = get_persian_day_name(jalali_date)
                        persian_month_name = get_persian_month_name(jalali_date)
                        
                        persian_day_num = to_persian_numerals(str(jalali_date.day))
                        persian_year_num = to_persian_numerals(str(jalali_date.year))
                        persian_time_str = to_persian_numerals(dt_tehran.strftime("%H:%M"))
                        formatted_datetime_persian = f"{persian_day_name} {persian_day_num} {persian_month_name} {persian_year_num}، ساعت {persian_time_str}"
                        
                        reminder_index = offset + i + 1
                        response_lines.append(f"{to_persian_numerals(str(reminder_index))}. {reminder.task} ({formatted_datetime_persian}) [/del_{reminder.id}]")
                    response_text = "\n".join(response_lines)

                    total_pages = (total_reminders + reminders_per_page - 1) // reminders_per_page
                    if total_pages > 1:
                        keyboard_buttons = []
                        if page > 1:
                            keyboard_buttons.append({"text": f"⬅️ صفحه قبل ({to_persian_numerals(str(page-1))})", "callback_data": f"view_reminders:page:{page-1}"})
                        if page < total_pages:
                            keyboard_buttons.append({"text": f"صفحه بعد ({to_persian_numerals(str(page+1))}) ➡️", "callback_data": f"view_reminders:page:{page+1}"})
                        
                        clear_filters_cb_data = f"clear_filters_view_reminders:page:1" if active_filters else None
                        if clear_filters_cb_data:
                            if keyboard_buttons: 
                                keyboard_buttons.insert(0, {"text": "Clear Filters 🗑️", "callback_data": clear_filters_cb_data})
                            else: 
                                keyboard_buttons = [[{"text": "Clear Filters 🗑️", "callback_data": clear_filters_cb_data}]]
                        
                        if keyboard_buttons:
                           if not any(isinstance(el, list) for el in keyboard_buttons):
                               response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": [keyboard_buttons]}
                           else: 
                               response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": keyboard_buttons}

            except Exception as e:
                logger.error(f"Error fetching reminders for user_db_id {user_db_id}: {e}", exc_info=True)
                response_text = "خطایی در دریافت لیست یادآورهای شما رخ داد."
            finally:
                db.close()
            
    elif current_intent == "intent_delete_reminder":
        response_text = "لطفاً بگویید کد یادآوری که می‌خواهید حذف کنید را وارد کنید."

    elif current_intent == "intent_payment_initiate":
        response_text = "لطفاً بگویید کد پرداختی که می‌خواهید انجام دهید را وارد کنید."

    elif current_intent == "intent_help":
        response_text = settings.MSG_HELP 

    elif current_intent == "intent_greeting":
        response_text = "سلام! چطور می‌توانم امروز به شما کمک کنم؟"

    elif current_intent == "intent_farewell":
        response_text = "خدانگهدار!"

    elif current_intent == "intent_affirmation":
        response_text = "متوجه شدم."

    elif current_intent == "intent_negation":
        response_text = "باشه."

    elif current_intent == "intent_clarification_needed": 
        response_text = "متاسفانه منظور شما را کامل متوجه نشدم. می‌توانید واضح‌تر بگویید یا از دستور /cancel برای شروع مجدد استفاده کنید."
    elif current_intent == "unknown_intent" and extracted_parameters.get("error_in_nlu"):
        response_text = f"خطایی در پردازش زبان طبیعی درخواست شما رخ داد. لطفا دوباره تلاش کنید."
    elif current_intent == "unknown_intent":
        raw_input_text = state.get("input_text", "") 
        response_text = f"متاسفانه منظور شما از «{raw_input_text}» را متوجه نشدم. برای راهنمایی /help را ارسال کنید."
    
    # Fallback for any other unhandled confirmed/cancelled intents that might not have a status
    # or for confirmed intents that didn't result in 'success' (e.g., an error during creation after confirmation)
    # This ensures they don't fall through to the generic "کاری که از من خواستید..."
    elif current_intent == "intent_create_reminder_confirmed": # and status is not 'success'
        # This case implies confirmation happened, but creation itself might have failed.
        # create_reminder_node would have set an error message.
        pre_set_text = state.get("response_text")
        if pre_set_text and reminder_creation_status != "success": # Ensure it's not the success message
             response_text = pre_set_text
             response_keyboard_markup = None # Usually no keyboard on error/alternative flow
             logger.info(f"Using pre-set response for confirmed reminder (non-success status: {reminder_creation_status}): '{response_text}'")
        else: # Fallback generic confirmation if no specific error message was set
            response_text = "وضعیت ایجاد یادآور نامشخص است. لطفا بررسی کنید یا دوباره تلاش نمایید."
            response_keyboard_markup = None


    ai_message_content = response_text 

    logger.info(f"User {user_id}: Response for intent='{current_intent}': '{response_text[:200]}...'")
    
    base_return = {
        "response_text": response_text, 
        "response_keyboard_markup": response_keyboard_markup,
        "current_node_name": "handle_intent_node",
        "messages": [AIMessage(content=ai_message_content)] 
    }
    
    final_return_state = updated_state_dict.copy() 
    final_return_state.update(base_return) 

    return final_return_state

async def format_response_node(state: AgentState) -> Dict[str, Any]:
    """Formats the response_text and keyboard for the bot to send.
    Also adds the AI message to the graph's internal message history if applicable.
    This node is typically the last one before END for most user-visible interactions.
    """
    user_id = state.get("user_id")
    response = state.get("response_text")
    keyboard_markup = state.get("response_keyboard_markup")

    logger.debug(f"format_response_node for user {user_id}: Received response_text type: {type(response)}, value: '{response}', keyboard: {bool(keyboard_markup)}")

    messages_to_add = [] # For LangGraph's internal state.messages if using add_messages

    # Only attempt to create AIMessage if response_text is a non-empty string
    if isinstance(response, str) and response.strip():
        logger.info(f"Formatting response for user {user_id}: '{response[:100]}...' with keyboard: {bool(keyboard_markup)}")
        try:
            ai_message_to_add = AIMessage(content=response) 
            messages_to_add.append(ai_message_to_add)
        except Exception as e:
            logger.error(f"Error creating AIMessage in format_response_node for user {user_id}: {e}", exc_info=True)
            # Decide if we should clear response_text or let it pass through if AIMessage fails
            # For now, let it pass; the bot sending logic will handle it.
    elif response is not None: # It's not a non-empty string, but it's not None (e.g. empty string, or wrong type)
        logger.warning(f"format_response_node for user {user_id}: response_text is present but not a non-empty string (type: {type(response)}, value: '{response}'). Not adding to AIMessage history. Bot will send as is.")
    else: # response is None
        logger.info(f"format_response_node for user {user_id}: No response_text provided. Nothing to format for AIMessage history.")

    # This node's primary job for the bot is to pass through the text and keyboard.
    # The 'messages' key is for LangGraph's state if using Annotated[List[BaseMessage], add_messages]
    # which we are not explicitly using for now, but good practice to prepare for it.
    return {
        "response_text": response, 
        "response_keyboard_markup": keyboard_markup,
        "messages": messages_to_add, # This list will be empty if response was not a non-empty string
        "current_node_name": "format_response_node"
    }

async def process_reminder_filters_node(state: AgentState) -> Dict[str, Any]:
    """Processes extracted filter parameters (date_phrase, keywords)
    and updates reminder_filters in AgentState.
    Uses resolve_persian_date_phrase_to_range for date phrases.
    """
    user_id = state.get("user_id")
    logger.info(f"Graph: Entered process_reminder_filters_node for user {user_id}")
    
    extracted_params = state.get("extracted_parameters", {})
    updated_reminder_filters: Dict[str, Any] = {} 
    filter_status_message: Optional[str] = None

    # Check if the action is to clear filters first
    if extracted_params.get("clear_filters_action") is True:
        logger.info(f"User {user_id}: Clearing all reminder filters due to clear_filters_action.")
        # updated_reminder_filters remains empty, and we skip other processing.
        return {
            "reminder_filters": updated_reminder_filters,
            "current_node_name": "process_reminder_filters_node",
            "filter_processing_status_message": "فیلترها پاک شدند." # Provide feedback
        }

    date_phrase = extracted_params.get("date_phrase")
    keywords = extracted_params.get("keywords") 

    if date_phrase:
        logger.info(f"User {user_id}: Processing date_phrase for filter: '{date_phrase}'")
        updated_reminder_filters["raw_date_phrase"] = date_phrase
        try:
            start_utc, end_utc = resolve_persian_date_phrase_to_range(date_phrase)
            if start_utc and end_utc:
                updated_reminder_filters["date_start_utc"] = start_utc
                updated_reminder_filters["date_end_utc"] = end_utc
                logger.info(f"User {user_id}: Resolved date_phrase '{date_phrase}' to UTC range: {start_utc} - {end_utc}")
            else:
                logger.warning(f"User {user_id}: Could not resolve date_phrase '{date_phrase}' to a valid range.")
                filter_status_message = settings.MSG_FILTER_DATE_PARSE_ERROR.format(phrase=date_phrase)
        except Exception as e:
            logger.error(f"User {user_id}: Error resolving date_phrase '{date_phrase}': {e}", exc_info=True)
            filter_status_message = settings.MSG_FILTER_DATE_PARSE_ERROR.format(phrase=date_phrase)
    
    if keywords:
        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
            cleaned_keywords = [k.strip() for k in keywords if k.strip()]
            if cleaned_keywords:
                updated_reminder_filters["keywords"] = cleaned_keywords
                logger.info(f"User {user_id}: Using keywords for filter: {cleaned_keywords}")
        else:
            logger.warning(f"User {user_id}: 'keywords' parameter was not a list of strings: {keywords}. Ignoring.")
            # Potentially add a message to filter_status_message if keywords were expected but malformed

    # Handling of "clear filters"
    # If intent was /reminders and no filter params are extracted by NLU,
    # it implies a request for an unfiltered list.
    # We should clear any existing filters in the state.
    # This logic might be better placed in the router or if determine_intent clears filters for plain /reminders.
    # For now, if no new filters are extracted by NLU for a view_reminders intent,
    # this node will return empty `updated_reminder_filters` if it was a fresh call.
    # If state.get("reminder_filters") had old values, this node currently clears them if no new ones are parsed.

    # If no filters were successfully processed from NLU, and no error message generated yet,
    # but the intent was to view reminders with some text that NLU didn't pick up as filters:
    if not date_phrase and not keywords and extracted_params.get("original_text_for_filter_attempt"): # A hypothetical field NLU could set
        # filter_status_message = settings.MSG_FILTER_NO_CRITERIA_FOUND.format(text=extracted_params["original_text_for_filter_attempt"])
        pass


    # If NLU itself had an error producing filter params:
    if extracted_params.get("error_in_filter_nlu"): # Another hypothetical field
        # filter_status_message = settings.MSG_FILTER_NLU_ERROR.format(text=state.get("input_text",""))
        pass
        
    output = {
        "reminder_filters": updated_reminder_filters, # This will overwrite existing filters in AgentState
        "current_node_name": "process_reminder_filters_node"
    }
    if filter_status_message:
        # This message can be picked up by handle_intent_node to display to the user.
        # It's better than this node directly trying to set response_text, as handle_intent_node
        # is the central place for crafting user responses.
        output["filter_processing_status_message"] = filter_status_message
        logger.info(f"User {user_id}: Filter processing resulted in status message: {filter_status_message}")

    return output

# Conditional Edges (Router functions)
def route_after_intent_determination(state: AgentState):
    """Router function to decide next step after intent determination."""
    intent = state.get("current_intent")
    if intent == "unknown_intent":
        logger.info("Routing to handle_intent_node for unknown_intent (will generate default response).")
        # Even unknown intent goes to handle_intent_node which then formulates a default unknown message.
        # This ensures AIMessage is consistently added.
        return "handle_intent_node" 
    logger.info(f"Routing to handle_intent_node for intent: {intent}")
    return "handle_intent_node" 