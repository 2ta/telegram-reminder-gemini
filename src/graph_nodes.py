import logging
from typing import Dict, Any, Optional
import json
import google.generativeai as genai
import datetime
import pytz
import jdatetime
import urllib.parse
import uuid 
import re # <--- ADDING IMPORT RE HERE
from sqlalchemy import func, or_
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import secrets

# Import our Persian formatting utilities
from src.persian_utils import to_persian_numerals, get_persian_day_name, get_persian_month_name, format_jalali_date

from src.graph_state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage
from config.config import settings, MSG_WELCOME, MSG_REMINDER_SET, MSG_LIST_EMPTY_NO_REMINDERS, MSG_PAYMENT_PROMPT, MSG_PAYMENT_BUTTON
from src.datetime_utils import parse_persian_datetime_to_utc, resolve_persian_date_phrase_to_range
from src.models import Reminder, User, SubscriptionTier
from src.database import get_db
from sqlalchemy.orm import Session

# Global cache for pending reminder details before confirmation
PENDING_REMINDER_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger(__name__)

# Helper function to get current Persian date and time for the LLM prompt
def get_current_persian_datetime_for_prompt() -> str:
    try:
        now_utc = datetime.datetime.now(pytz.utc)
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = now_utc.astimezone(tehran_tz)
        jalali_dt = jdatetime.datetime.fromgregorian(datetime=now_tehran)

        # Assuming get_persian_day_name and get_persian_month_name are correctly imported or defined
        # And to_persian_numerals is also available
        day_name = get_persian_day_name(jalali_dt) # Make sure this function handles jdatetime object
        day_num = to_persian_numerals(str(jalali_dt.day))
        month_name = get_persian_month_name(jalali_dt) # Make sure this function handles jdatetime object
        year_num = to_persian_numerals(str(jalali_dt.year))
        time_str = to_persian_numerals(now_tehran.strftime("%H:%M"))
        
        return f"{day_name} {day_num} {month_name} {year_num}، ساعت {time_str}"
    except Exception as e:
        logger.error(f"Error generating current Persian datetime for prompt: {e}", exc_info=True)
        return "تاریخ و زمان فعلی نامشخص"

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

    # --- Priority 1: Exact Callbacks ---
    if message_type == "callback_query":
        if effective_input.startswith("confirm_create_reminder:yes:id="):
            logger.info(f"DEBUG: Matched callback for 'confirm_create_reminder:yes:id=': {effective_input}")
            try:
                confirmation_id = effective_input.split("confirm_create_reminder:yes:id=", 1)[1]
                retrieved_data = PENDING_REMINDER_CONFIRMATIONS.pop(confirmation_id, None)
                if not retrieved_data:
                    logger.warning(f"Confirmation ID '{confirmation_id}' not found in cache for {effective_input}. Current cache keys: {list(PENDING_REMINDER_CONFIRMATIONS.keys())}")
                    return {
                        "current_intent": "unknown_intent",
                        "response_text": "این یادآور قبلاً ثبت شده یا منقضی شده.",
                        "current_node_name": "determine_intent_node"
                    }
                task = retrieved_data.get("task")
                parsed_dt_utc = retrieved_data.get("parsed_dt_utc")
                chat_id_from_cache = retrieved_data.get("chat_id")
                if not (task and parsed_dt_utc and chat_id_from_cache):
                    logger.error(f"Incomplete data from cache for ID {confirmation_id}. Retrieved: {retrieved_data}")
                    return {
                        "current_intent": "unknown_intent",
                        "response_text": "خطا: اطلاعات تاییدیه ناقص است (کش).",
                        "current_node_name": "determine_intent_node"
                    }
                populated_context = {
                    "collected_task": task,
                    "collected_parsed_datetime_utc": parsed_dt_utc,
                    "chat_id_for_creation": chat_id_from_cache
                }
                logger.info(f"Restored context from cache ID {confirmation_id}: {populated_context}")
                return {
                    "current_intent": "intent_create_reminder_confirmed",
                    "extracted_parameters": {},
                    "current_node_name": "determine_intent_node",
                    "reminder_creation_context": populated_context,
                    "pending_confirmation": None
                }
            except Exception as e:
                logger.error(f"Error processing 'yes:id' callback '{effective_input}': {e}", exc_info=True)
                return {
                    "current_intent": "unknown_intent",
                    "response_text": "خطا در پردازش تاییدیه.",
                    "current_node_name": "determine_intent_node"
                }
        elif effective_input.startswith("confirm_create_reminder:no:id="):
            logger.info(f"DEBUG: Matched callback for 'confirm_create_reminder:no:id=': {effective_input}")
            try:
                confirmation_id = effective_input.split("confirm_create_reminder:no:id=", 1)[1]
                if confirmation_id in PENDING_REMINDER_CONFIRMATIONS:
                    PENDING_REMINDER_CONFIRMATIONS.pop(confirmation_id)
                    logger.info(f"Removed pending confirmation {confirmation_id} due to 'no' callback.")
                    return {
                        "current_intent": "intent_create_reminder_cancelled",
                        "response_text": "باشه، تنظیمش نکردم ❌\nفقط کافیه دوباره بگی چی رو کی یادت بندازم 🙂",
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": {},
                        "pending_confirmation": None
                    }
                else:
                    logger.warning(f"Confirmation ID {confirmation_id} not found in cache for 'no' callback {effective_input}")
                    return {
                        "current_intent": "unknown_intent",
                        "response_text": "این درخواست قبلاً لغو شده است یا منقضی شده.",
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": {},
                        "pending_confirmation": None
                    }
            except Exception as e:
                logger.error(f"Error cleaning up pending confirmation for ID in '{effective_input}': {e}", exc_info=True)
                return {
                    "current_intent": "unknown_intent",
                    "response_text": "خطا در پردازش لغو تاییدیه.",
                    "current_node_name": "determine_intent_node",
                    "reminder_creation_context": {},
                    "pending_confirmation": None
                }
        elif effective_input == "confirm_create_reminder:no": # Deprecated branch
            logger.warning(f"DEBUG: Matched DEPRECATED callback for 'confirm_create_reminder:no': {effective_input}. Should include ID.")
            return {
                "current_intent": "intent_create_reminder_cancelled",
                "response_text": "باشه، تنظیمش نکردم ❌\nفقط کافیه دوباره بگی چی رو کی یادت بندازم 🙂",
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": {},
                "pending_confirmation": None
            }
        elif effective_input.startswith("confirm_delete_reminder:"):
            try:
                reminder_id_str = effective_input.split("confirm_delete_reminder:", 1)[1]
                reminder_id = int(reminder_id_str)
                logger.info(f"DEBUG: Matched callback for 'confirm_delete_reminder:{reminder_id}'")
                return {
                    "current_intent": "intent_confirm_delete_reminder",
                    "extracted_parameters": {"reminder_id_to_confirm_delete": reminder_id},
                    "current_node_name": "determine_intent_node"
                }
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing confirm_delete_reminder callback '{effective_input}': {e}", exc_info=True)
                return {"current_intent": "unknown_intent", "response_text": "خطا در پردازش درخواست حذف.", "current_node_name": "determine_intent_node"}
        elif effective_input.startswith("execute_delete_reminder:"):
            try:
                reminder_id_str = effective_input.split("execute_delete_reminder:", 1)[1]
                reminder_id = int(reminder_id_str)
                logger.info(f"DEBUG: Matched callback for 'execute_delete_reminder:{reminder_id}'")
                return {
                    "current_intent": "intent_delete_reminder_confirmed",
                    "extracted_parameters": {"reminder_id_to_delete": reminder_id},
                    "current_node_name": "determine_intent_node"
                }
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing execute_delete_reminder callback '{effective_input}': {e}", exc_info=True)
                return {"current_intent": "unknown_intent", "response_text": "خطا در پردازش دستور حذف.", "current_node_name": "determine_intent_node"}
        elif effective_input == "cancel_delete_reminder":
            logger.info(f"DEBUG: Matched callback for 'cancel_delete_reminder'")
            return {
                "current_intent": "intent_delete_reminder_cancelled",
                "response_text": "باشه، حذفش نکردم. یادآور شما فعال باقی می‌مونه 👍",
                "current_node_name": "determine_intent_node"
            }
        elif effective_input.startswith("view_reminders:page:"):
            try:
                page = int(effective_input.split("view_reminders:page:",1)[1])
                logger.info(f"Detected view_reminders pagination callback for page {page}")
                return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": page}, "current_node_name": "determine_intent_node"}
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing view_reminders pagination callback '{effective_input}': {e}", exc_info=True)
                return {"current_intent": "unknown_intent", "response_text": "خطا در پردازش صفحه بندی.", "current_node_name": "determine_intent_node"}
        elif effective_input == "show_subscription_options":
            logger.info(f"Detected 'show_subscription_options' callback.")
            return {"current_intent": "intent_show_payment_options", "current_node_name": "determine_intent_node"}
        elif effective_input == "initiate_payment_zibal":
            logger.info(f"Detected 'initiate_payment_zibal' callback.")
            return {"current_intent": "intent_payment_initiate_zibal", "current_node_name": "determine_intent_node"}
        elif effective_input == "initiate_payment_zibal_confirmed":
            logger.info(f"Detected 'initiate_payment_zibal_confirmed' callback.")
            return {"current_intent": "intent_create_zibal_link", "current_node_name": "determine_intent_node"}

    # --- Priority 2: Explicit Commands and Keyboard Buttons ---
    if input_text.startswith('/'):
        if input_text == '/start':
            logger.info(f"Detected /start command from user {state.get('user_id')}")
            return {"current_intent": "intent_start", "current_node_name": "determine_intent_node"}
        elif input_text == '/reminders' or input_text.startswith('/reminders '):
            page = 1
            if input_text.startswith('/reminders '): # Check if there's an argument
                try:
                    page_arg = input_text.split('/reminders ', 1)[1]
                    if page_arg.isdigit():
                        page = int(page_arg)
                except (IndexError, ValueError): # Handles no argument or invalid argument
                    pass # Default to page 1
            logger.info(f"Detected /reminders command from user {state.get('user_id')}, page: {page}")
            return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": page}, "current_node_name": "determine_intent_node"}
        elif input_text.startswith('/del_'):
            try:
                reminder_id = int(input_text.split('_')[1])
                logger.info(f"Detected delete reminder command for ID {reminder_id} from user {state.get('user_id')}")
                # Changed to intent_confirm_delete_reminder to go through confirmation flow
                return {"current_intent": "intent_confirm_delete_reminder", "extracted_parameters": {"reminder_id_to_confirm_delete": reminder_id}, "current_node_name": "determine_intent_node"}
            except (IndexError, ValueError) as e:
                logger.warning(f"Invalid delete reminder command: {input_text}, error: {e}")
                return {"current_intent": "unknown_intent", "response_text": "فرمت دستور حذف نامعتبر است. لطفاً از دکمه حذف کنار یادآور استفاده کنید.", "current_node_name": "determine_intent_node"}
    
    if input_text == "یادآورهای من":
        logger.info(f"Detected 'یادآورهای من' text input from user {state.get('user_id')}")
        return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": 1}, "current_node_name": "determine_intent_node"}
    elif input_text == "یادآور نامحدود 👑": 
        logger.info(f"Detected 'یادآور نامحدود 👑' text input from user {state.get('user_id')}")
        return {"current_intent": "intent_show_payment_options", "current_node_name": "determine_intent_node"}

    # --- Priority 3: LLM for Potential Reminder Creation (General Text Input) ---
    if message_type == "text" or message_type == "voice":  # Voice messages are transcribed before reaching here
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. LLM NLU will be skipped.")
            # Fall through to unknown_intent at the end
        else:
            try:
                llm = ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL_NAME, temperature=0.3)
                current_persian_datetime = get_current_persian_datetime_for_prompt()
                prompt_template = f"""شما یک دستیار هوشمند برای تشخیص قصد کاربر از یک متن فارسی هستید.
وظیفه شما این است که مشخص کنید آیا کاربر قصد ایجاد یک یادآور جدید را دارد یا خیر.
اگر قصد ایجاد یادآور دارد، باید اطلاعات زیر را استخراج کنید:
1.  `task`: متن اصلی کار که باید یادآوری شود (مثلاً «زنگ زدن به برادرم»، «جلسه هفتگی تیم فروش»). این بخش نباید شامل تاریخ و زمان باشد.
2.  `date_str`: عبارت مربوط به تاریخ (مثلاً «فردا»، «پس فردا»، «شنبه آینده»، «آخر هفته»، «سه روز دیگه»، «۲۵ اسفند»). این فیلد می‌تواند شامل عبارات نسبی یا دقیق باشد.
3.  `time_str`: عبارت مربوط به زمان (مثلاً «ساعت ۱۴»، «۳ بعد از ظهر»، «صبح زود»، «نزدیک ظهر»). این فیلد می‌تواند شامل عبارات نسبی یا دقیق باشد.

تاریخ و زمان فعلی در تهران: {current_persian_datetime}

متن کاربر: «{input_text}»

لطفاً پاسخ خود را فقط و فقط در قالب یک آبجکت JSON با ساختار زیر ارائه دهید:
{{
  \"is_reminder_creation_intent\": boolean,
  \"task\": \"string or null\",
  \"date_str\": \"string or null\",
  \"time_str\": \"string or null\"
}}"""
                logger.info(f"Sending prompt to LLM for intent determination. User input: '{input_text}'")
                llm_response = await llm.ainvoke([HumanMessage(content=prompt_template)])
                llm_response_content = llm_response.content.strip()
                logger.debug(f"LLM raw response: {llm_response_content}")
                try:
                    # Attempt to extract JSON even if it's embedded in other text
                    json_match = re.search(r"```json\s*(\{.*?\})\s*```", llm_response_content, re.DOTALL)
                    json_str = json_match.group(1) if json_match else llm_response_content
                    parsed_llm_response = json.loads(json_str)
                    is_reminder_intent = parsed_llm_response.get("is_reminder_creation_intent", False)
                    if is_reminder_intent:
                        task = parsed_llm_response.get("task")
                        date_str = parsed_llm_response.get("date_str")
                        time_str = parsed_llm_response.get("time_str")
                        if task and (date_str or time_str):  # Need at least a task and some date/time info
                            logger.info(f"LLM determined 'intent_create_reminder'. Task: '{task}', Date: '{date_str}', Time: '{time_str}'")
                            return {
                                "current_intent": "intent_create_reminder",
                                "extracted_parameters": {"date": date_str, "time": time_str, "task": task},
                                "current_node_name": "determine_intent_node",
                                "reminder_creation_context": {
                                    "collected_task": task,
                                    "collected_date_str": date_str,
                                    "collected_time_str": time_str,
                                    "pending_clarification_type": None
                                }
                            }
                        else:
                            logger.warning(f"LLM indicated reminder intent, but task or all date/time info is missing. LLM Output: {parsed_llm_response}")
                            # Fall through to unknown_intent if critical parts are missing
                    else:
                        logger.info(f"LLM determined 'is_reminder_creation_intent' is false for input: '{input_text}'")
                        # Fall through to unknown_intent
                except json.JSONDecodeError as json_e:
                    logger.error(f"Failed to parse JSON response from LLM: {json_e}. Raw response for user '{state.get('user_id')}': {llm_response_content}")
                    # Fall through to unknown_intent
                except Exception as e:
                    logger.error(f"Error parsing LLM response for user '{state.get('user_id')}': {e}", exc_info=True)
                    # Fall through to unknown_intent
            except Exception as e:
                logger.error(f"Error during LLM call in determine_intent_node for user '{state.get('user_id')}': {e}", exc_info=True)
                # Fall through to unknown_intent

    # --- Default Fallback (Unknown Intent) ---
    logger.warning(f"Could not determine a specific intent for user '{state.get('user_id')}', input: '{input_text}'. Treating as unknown_intent.")
    current_reminder_creation_context = state.get("reminder_creation_context") if state.get("reminder_creation_context") is not None else {}
    # Using the more specific message for unknown intent when reminder creation is the primary NLU focus now
    unknown_intent_response_text = (
        f"متاسفانه منظور شما از «{input_text}» را برای ایجاد یادآور متوجه نشدم. "
        "لطفاً کار، تاریخ و زمان مورد نظرتان را واضح‌تر بیان کنید. مثلا: «یادم بنداز فردا ساعت ۱۰ صبح به دکتر زنگ بزنم»"
    )
    return {
        "current_intent": "unknown_intent",
        "extracted_parameters": {"input_was": input_text}, 
        "response_text": unknown_intent_response_text,
        "current_node_name": "determine_intent_node",
        "reminder_creation_context": current_reminder_creation_context # Pass through context
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
        
        # No inline keyboard here anymore, the persistent reply keyboard is set in bot.py
        logger.info(f"Sending welcome message without specific inline keyboard.")

        return {
            "response_text": MSG_WELCOME,
            "response_keyboard_markup": None, # Explicitly None
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
                    [{"text": "یادآور نامحدود 👑", "callback_data": "show_subscription_options"}]
                ]
            }

        return {
            "current_operation_status": "error_limit_exceeded", # MODIFIED KEY
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
        "current_operation_status": new_reminder_creation_status, # MODIFIED KEY (this holds statuses like 'clarification_needed_task', 'ready_for_confirmation')
        "current_node_name": "validate_and_clarify_reminder_node"
    }

async def confirm_reminder_details_node(state: AgentState) -> Dict[str, Any]:
    """Asks the user to confirm the details of the reminder before creation."""
    logger.info(f"Graph: Entered confirm_reminder_details_node for user {state.get('user_id')}")
    
    user_id = state.get("user_id")
    chat_id = state.get("chat_id") # Get chat_id from state (should be set by bot_handlers)
    if not chat_id: # Fallback to user_id if chat_id is not in state directly for some reason
        chat_id = user_id 
        logger.warning(f"chat_id not found directly in state for user {user_id}, using user_id as chat_id for confirmation cache.")


    reminder_context = state.get("reminder_creation_context")
    if not reminder_context or not reminder_context.get("collected_task") or not reminder_context.get("collected_parsed_datetime_utc"):
        logger.error(f"Missing task or datetime in reminder_creation_context for confirmation: {reminder_context}")
        return {
            "response_text": "خطا: اطلاعات یادآور برای تایید کامل نیست. لطفاً دوباره تلاش کنید.",
            "current_node_name": "confirm_reminder_details_node",
            "pending_confirmation": None # Ensure this is cleared
        }

    task = reminder_context["collected_task"]
    parsed_dt_utc_val = reminder_context["collected_parsed_datetime_utc"]

    # Fix: handle both str and datetime types, use only top-level import
    if isinstance(parsed_dt_utc_val, str):
        try:
            parsed_dt_utc = datetime.datetime.fromisoformat(parsed_dt_utc_val.replace("Z", "+00:00"))
        except Exception as e:
            logger.error(f"Invalid datetime string in reminder_creation_context: {parsed_dt_utc_val}. Error: {e}")
        return {
            "response_text": "خطا: فرمت تاریخ و زمان ارسال شده برای تایید نامعتبر است.",
                "current_node_name": "confirm_reminder_details_node",
                "pending_confirmation": None
            }
    elif isinstance(parsed_dt_utc_val, datetime.datetime):
        parsed_dt_utc = parsed_dt_utc_val
    else:
        logger.error(f"Missing or invalid type for datetime in reminder_creation_context: {parsed_dt_utc_val} (type: {type(parsed_dt_utc_val)})")
        return {
            "response_text": "خطا: تاریخ و زمان یادآور برای تایید یافت نشد.",
            "current_node_name": "confirm_reminder_details_node",
            "pending_confirmation": None
        }

    tehran_tz = pytz.timezone("Asia/Tehran")
    parsed_dt_tehran = parsed_dt_utc.astimezone(tehran_tz)
    jalali_dt = jdatetime.datetime.fromgregorian(datetime=parsed_dt_tehran)

    # Instead of: formatted_date_time = format_jalali_date(jalali_dt, include_time=True, include_day_name=True)
    formatted_date = format_jalali_date(jalali_dt)
    # Manually append time in Persian numerals
    persian_time_str = to_persian_numerals(parsed_dt_tehran.strftime("%H:%M"))
    formatted_date_time = f"{formatted_date}، ساعت {persian_time_str}"

    confirmation_id = secrets.token_hex(4)  # 8 hex chars, 32 bits of entropy
    
    # Store details for confirmation
    # Ensure chat_id is available, it's crucial for sending the reminder later if not directly in state at create_reminder_node
    if not chat_id:
        logger.error(f"CRITICAL: chat_id is None when trying to cache confirmation for user {user_id}. This will cause issues.")
        # Attempt to get it from user_telegram_details if available
        user_details = state.get("user_telegram_details")
        if user_details and user_details.get("chat_id"):
            chat_id = user_details.get("chat_id")
            logger.info(f"Retrieved chat_id ({chat_id}) from user_telegram_details for caching.")
        else: # Still no chat_id, this is a problem.
             # For now, we will proceed but log a severe warning. The reminder might not be sendable
             # to the right chat if it's a group/channel and chat_id isn't captured early.
             # As a last resort, if we assume it's a private chat, chat_id equals user_id.
             # This assumption might be wrong in group/channel contexts.
             chat_id = user_id # Fallback to user_id, with prior logging about potential issue

    PENDING_REMINDER_CONFIRMATIONS[confirmation_id] = {
        "task": task,
        "parsed_dt_utc": parsed_dt_utc_val, # Store as string, will be parsed again
        "chat_id": chat_id # Store chat_id
    }
    logger.info(f"DEBUG: Stored pending confirmation for ID {confirmation_id} with task='{task}', dt='{parsed_dt_utc_val}', chat_id='{chat_id}'. Cache size: {len(PENDING_REMINDER_CONFIRMATIONS)}")


    # Use the cleaned, extracted task for confirmation
    def clean_task_text(task: str) -> str:
        import re
        if not isinstance(task, str):
            return ""
        task = task.strip()
        task = re.sub(r'[\.,!؟]+$', '', task)
        task = re.sub(r'\s+', ' ', task)
        return task

    task = clean_task_text(reminder_context.get("collected_task", ""))
    response_text = (
        "یادآور زیر رو تنظیم کنم؟ 👇\n\n"
        f"📝 متن: {task}\n"
        f"⏰ زمان: {formatted_date_time}\n\n"
        "اگه درسته، روی «تنظیم کن» بزن\n"
        "اگه نیاز به تغییر داره، روی «رد» بزن و یادآور جدید رو دوباره بفرست 🙂"
    )
    
    # Confirmation message keyboard (styled as in the image, using dict format for compatibility)
    keyboard_markup = {
        "type": "InlineKeyboardMarkup",
        "inline_keyboard": [
            [
                {"text": "✅ تنظیم کن", "callback_data": f"confirm_create_reminder:yes:id={confirmation_id}"},
                {"text": "❌ رد", "callback_data": f"confirm_create_reminder:no:id={confirmation_id}"}
            ]
        ]
    }
    
    return {
        "response_text": response_text,
        "response_keyboard_markup": keyboard_markup,
        "current_node_name": "confirm_reminder_details_node",
        "pending_confirmation": {"task": task, "datetime_utc_str": parsed_dt_utc_val, "confirmation_id": confirmation_id} # Keep some info for state if needed
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
                    "current_operation_status": "error_invalid_datetime_format_in_context", # MODIFIED KEY
                    "response_text": "خطا: فرمت تاریخ و زمان ذخیره شده نامعتبر است.",
                    "current_node_name": "create_reminder_node",
                    "reminder_creation_context": reminder_ctx,
                    "pending_confirmation": None
                }
        else:
            logger.error(f"Invalid datetime in context for user {user_id}. Task: {task}, DT: {parsed_dt_utc_from_ctx} (type: {type(parsed_dt_utc_from_ctx)}) ")
            return {
                "current_operation_status": "error_missing_details", # MODIFIED KEY
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
            "current_operation_status": "error_missing_details", # MODIFIED KEY
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
                db_temp.close()
                return {"current_operation_status": "error_user_not_found", "response_text": "خطا: کاربر برای ایجاد یادآور یافت نشد.", "current_node_name": "create_reminder_node", "pending_confirmation": None} # MODIFIED KEY
        finally:
            db_temp.close()
    
    user_db_id = user_profile.get("user_db_id")
    if not user_db_id: # Should not happen if above logic works
        logger.error(f"Critical: user_db_id still missing for user {user_id} before DB operation.")
        return {"current_operation_status": "error_internal_user_id_missing", "response_text": "خطای داخلی: شناسه کاربر موجود نیست.", "current_node_name": "create_reminder_node", "pending_confirmation": None} # MODIFIED KEY

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
        # Clean up the extracted task before saving
        def clean_task_text(task: str) -> str:
            import re
            if not isinstance(task, str):
                return ""
            # Remove leading/trailing whitespace
            task = task.strip()
            # Remove trailing punctuation (.,!؟)
            task = re.sub(r'[\.,!؟]+$', '', task)
            # Collapse multiple spaces
            task = re.sub(r'\s+', ' ', task)
            return task

        task = clean_task_text(reminder_ctx.get("collected_task", ""))
        new_reminder = Reminder(
            user_id=user_db_id,  # Use the user's actual DB ID
            task=task,
            jalali_date_str=jalali_date_str, 
            time_str=time_str, 
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
            "تمومه! 🎉  \n"
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
            "current_operation_status": "success", # MODIFIED KEY
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
            "current_operation_status": "error_db_create", # MODIFIED KEY
            "response_text": "متاسفانه در ایجاد یادآور شما در پایگاه داده خطایی رخ داد.",
            "current_node_name": "create_reminder_node",
            "reminder_creation_context": reminder_ctx, # Keep context for potential retry/debug
            "pending_confirmation": None
        }
    finally:
        db.close()

async def confirm_delete_reminder_node(state: AgentState) -> Dict[str, Any]:
    """Asks the user to confirm if they want to delete the specified reminder."""
    user_id = state.get("user_id")
    extracted_params = state.get("extracted_parameters", {})
    reminder_id_to_confirm = extracted_params.get("reminder_id_to_confirm_delete")

    logger.info(f"Graph: Entered confirm_delete_reminder_node for user {user_id}, reminder_id: {reminder_id_to_confirm}")

    if reminder_id_to_confirm is None:
        logger.error(f"confirm_delete_reminder_node: reminder_id_to_confirm_delete is missing from extracted_parameters for user {user_id}")
        return {
            "response_text": "خطا: شناسه یادآور برای تایید حذف مشخص نیست.",
            "current_node_name": "confirm_delete_reminder_node"
        }

    db: Session = next(get_db())
    try:
        user_db_id = state.get("user_profile", {}).get("user_db_id")
        if not user_db_id:
            logger.error(f"confirm_delete_reminder_node: user_db_id not found in profile for user {user_id}")
            return {"response_text": "خطا: اطلاعات کاربری برای تایید حذف یافت نشد.", "current_node_name": "confirm_delete_reminder_node"}

        reminder = db.query(Reminder).filter(
            Reminder.id == reminder_id_to_confirm,
            Reminder.user_id == user_db_id,
            Reminder.is_active == True 
        ).first()

        if not reminder:
            logger.warning(f"confirm_delete_reminder_node: Reminder ID {reminder_id_to_confirm} not found, not active, or doesn't belong to user {user_id}.")
            return {
                "response_text": "یادآور مورد نظر برای حذف یافت نشد یا قبلاً حذف شده است.",
                "current_node_name": "confirm_delete_reminder_node"
            }

        # Format reminder details for confirmation message
        task_preview = reminder.task[:50] + "..." if len(reminder.task) > 50 else reminder.task
        try:
            gregorian_dt = reminder.gregorian_datetime
            if not gregorian_dt:
                formatted_datetime_persian = "[تاریخ نامشخص]"
            else:
                tehran_tz = pytz.timezone("Asia/Tehran")
                dt_tehran = gregorian_dt.astimezone(tehran_tz)
                jalali_date_obj = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
                
                persian_day_name = get_persian_day_name(jalali_date_obj)
                persian_month_name = get_persian_month_name(jalali_date_obj)
                persian_day_num = to_persian_numerals(str(jalali_date_obj.day))
                persian_year_num = to_persian_numerals(str(jalali_date_obj.year))
                persian_time_str = to_persian_numerals(dt_tehran.strftime("%H:%M"))
                formatted_datetime_persian = f"{persian_day_name} {persian_day_num} {persian_month_name} {persian_year_num}، ساعت {persian_time_str}"
        except Exception as e:
            logger.error(f"Error formatting date for reminder {reminder.id} in confirm_delete: {e}")
            formatted_datetime_persian = "[خطا در نمایش تاریخ]"

        confirmation_message = (
            f"⚠️ آیا از حذف یادآور زیر مطمئن هستید؟\n\n"
            f"📝 **یادآور**: {task_preview}\n"
            f"⏰ **زمان**: {formatted_datetime_persian}"
        )
        
        confirmation_keyboard = {
                    "type": "InlineKeyboardMarkup",
                    "inline_keyboard": [
                [
                    {"text": "بله، حذف کن ✅", "callback_data": f"execute_delete_reminder:{reminder.id}"},
                    {"text": "نه، منصرف شدم ❌", "callback_data": "cancel_delete_reminder"}
                ]
            ]
        }
        logger.info(f"Prepared delete confirmation for user {user_id}, reminder ID {reminder.id}")
        return {
            "response_text": confirmation_message,
            "response_keyboard_markup": confirmation_keyboard,
            "pending_confirmation": "delete_reminder", # Flag that we are awaiting delete confirmation
            "current_node_name": "confirm_delete_reminder_node"
        }

    except Exception as e:
        logger.error(f"Error in confirm_delete_reminder_node for user {user_id}, reminder ID {reminder_id_to_confirm}: {e}", exc_info=True)
        return {
            "response_text": "خطایی در آماده‌سازی پیام تایید حذف رخ داد. لطفاً دوباره تلاش کنید.",
            "current_node_name": "confirm_delete_reminder_node"
        }
    finally:
        db.close()

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Handles the determined intent, e.g., fetching reminders, preparing help message."""
    current_intent = state.get("current_intent")
    user_id = state.get("user_id")
    user_profile = state.get("user_profile") # Ensure this is loaded, might be None
    extracted_parameters = state.get("extracted_parameters", {})
    current_operation_status = state.get("current_operation_status")
    logger.info(f"Graph: Entered handle_intent_node for user {user_id}, intent: {current_intent}, params: {extracted_parameters}, status: {current_operation_status}")

    default_response_text = "کاری که از من خواستید را متوجه نشدم. لطفاً واضح‌تر بگویید."
    response_text_from_state = state.get("response_text")
    response_text = response_text_from_state or default_response_text
    
    # Optimized initial response_text handling
    if current_intent == "intent_create_reminder_confirmed" and response_text_from_state and "تمومه! 🎉" in response_text_from_state:
        current_operation_status = "success" # Simulate for cleanup
    elif current_intent == "intent_create_reminder_cancelled" and response_text_from_state:
        pass # response_text is already set from determine_intent_node
    elif current_intent == "intent_delete_reminder_cancelled" and response_text_from_state:
        pass # response_text is already set
    elif not response_text_from_state: # If no specific message from prior nodes for other intents
        response_text = default_response_text

    response_keyboard_markup = state.get("response_keyboard_markup")
    updated_state_dict = {"current_node_name": "handle_intent_node"}

    # Helper directly in this scope or ensure it's imported/available if moved
    # def to_persian_numerals(text: str) -> str:
    #     persian_numerals_map = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    #     return str(text).translate(persian_numerals_map)

    if current_intent == "intent_start":
        response_text = MSG_WELCOME
        response_keyboard_markup = None
        logger.info(f"handle_intent_node processing intent_start for user {user_id}.")

    elif current_intent == "intent_view_reminders":
        logger.info(f"handle_intent_node: Preparing to view reminders for user {user_id}.")
        db: Session = next(get_db())
        try:
            if not user_profile or not user_profile.get("user_db_id"):
                logger.warning(f"User profile or user_db_id not found for user {user_id} when viewing reminders.")
                response_text = "اطلاعات کاربری شما یافت نشد. لطفاً دوباره سعی کنید."
            else:
                user_db_id = user_profile["user_db_id"]
                page = extracted_parameters.get("page", 1)
                page_size = settings.REMINDERS_PER_PAGE
                offset = (page - 1) * page_size
                
                reminders_query = db.query(Reminder).filter(
                    Reminder.user_id == user_db_id,
                    Reminder.is_active == True
                ).order_by(Reminder.jalali_date_str.asc(), Reminder.time_str.asc())
                
                total_reminders_count = reminders_query.count()
                reminders = reminders_query.offset(offset).limit(page_size).all()

                if not reminders and total_reminders_count == 0:
                    response_text = MSG_LIST_EMPTY_NO_REMINDERS
                    response_keyboard_markup = None
                elif not reminders and total_reminders_count > 0:
                    response_text = f"صفحه {to_persian_numerals(str(page))} خالی است. به صفحه قبل برگردید."
                    buttons = []
                    if page > 1:
                        buttons.append([{"text": "صفحه قبل ⬅️", "callback_data": f"view_reminders:page:{page-1}"}])
                    response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": buttons} if buttons else None
                else:
                    reminder_list_items_text = []
                    action_buttons = []
                    reminder_list_header = f"یادآورهای فعال شما (صفحه {to_persian_numerals(str(page))} از {to_persian_numerals(str((total_reminders_count + page_size - 1) // page_size))}):\\n\\n"
                    for reminder in reminders:
                        try:
                            gregorian_dt = reminder.gregorian_datetime
                            if not gregorian_dt:
                                logger.warning(f"Invalid datetime for reminder ID {reminder.id}. Skipping.")
                                reminder_list_items_text.append(f"⚠️ اطلاعات تاریخ و زمان برای یادآور با شناسه {reminder.id} نامعتبر است.")
                                continue
                            tehran_tz = pytz.timezone('Asia/Tehran')
                            aware_tehran_dt = tehran_tz.localize(gregorian_dt)
                            jalali_date_str_display = format_jalali_date(jdatetime.datetime.fromgregorian(datetime=aware_tehran_dt))
                            time_str_display = aware_tehran_dt.strftime('%H:%M')
                            day_name = get_persian_day_name(aware_tehran_dt.weekday())
                            task_preview = reminder.task[:40] + "..." if len(reminder.task) > 40 else reminder.task
                            reminder_item_text = (
                                f"📝 **{reminder.task}**\\n"
                                f"⏰ {day_name}، {jalali_date_str_display}، ساعت {to_persian_numerals(time_str_display)}"
                            )
                            reminder_list_items_text.append(reminder_item_text)
                            action_buttons.append([
                                {"text": f"حذف یادآور: «{task_preview}» 🗑️", "callback_data": f"confirm_delete_reminder:{reminder.id}"}
                            ])
                        except Exception as e:
                            logger.error(f"Error formatting reminder ID {reminder.id} for display: {e}", exc_info=True)
                            reminder_list_items_text.append(f"⚠️ خطای نمایشی برای یادآور با شناسه {reminder.id}")
                    
                    response_text = reminder_list_header + "\\n\\n--------------------\\n\\n".join(reminder_list_items_text)
                    if not reminder_list_items_text:
                        response_text = reminder_list_header + "موردی برای نمایش در این صفحه نیست."

                    pagination_row = []
                    if page > 1:
                        pagination_row.append({"text": "صفحه قبل ⬅️", "callback_data": f"view_reminders:page:{page-1}"})
                    if total_reminders_count > page * page_size:
                        pagination_row.append({"text": "➡️ صفحه بعد", "callback_data": f"view_reminders:page:{page+1}"})
                    
                    if pagination_row:
                        action_buttons.append(pagination_row)
                    if action_buttons:
                        response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": action_buttons}
                    else:
                        response_keyboard_markup = None
        except Exception as e:
            logger.error(f"Error fetching reminders for user {user_id}: {e}", exc_info=True)
            response_text = "خطا در دریافت لیست یادآورها. لطفاً دوباره تلاش کنید."
        finally:
            db.close()

    elif current_intent == "intent_delete_reminder" or current_intent == "intent_delete_reminder_confirmed":
        reminder_id_to_delete = None
        if current_intent == "intent_delete_reminder":
            reminder_id_to_delete = extracted_parameters.get("reminder_id")
        elif current_intent == "intent_delete_reminder_confirmed":
            reminder_id_to_delete = extracted_parameters.get("reminder_id_to_delete")
        
        delete_status = "unknown"
        deleted_task_name = ""

        if reminder_id_to_delete is not None and user_profile and user_profile.get("user_db_id"):
            db: Session = next(get_db())
            try:
                reminder_to_delete = db.query(Reminder).filter(
                    Reminder.id == reminder_id_to_delete,
                    Reminder.user_id == user_profile["user_db_id"]
                ).first()

                if reminder_to_delete:
                    if reminder_to_delete.is_active:
                        deleted_task_name = reminder_to_delete.task
                        reminder_to_delete.is_active = False
                        reminder_to_delete.updated_at = datetime.datetime.now(pytz.utc) # Use timezone aware
                        db.commit()
                        delete_status = "deleted"
                        if user_profile.get("current_reminder_count", 0) > 0: # Check if key exists
                             user_profile["current_reminder_count"] -=1
                    else:
                        delete_status = "already_inactive"
                else:
                    delete_status = "not_found"
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting reminder {reminder_id_to_delete} for user {user_id}: {e}", exc_info=True)
                delete_status = "error"
            finally:
                db.close()
        else:
            delete_status = "error_missing_info"

        if delete_status == "deleted":
            response_text = f"یادآور «{deleted_task_name}» با موفقیت حذف شد. ✅"
        elif delete_status == "already_inactive":
            response_text = "این یادآور قبلاً غیرفعال شده بود."
        elif delete_status == "not_found":
            response_text = "یادآور مورد نظر یافت نشد. ممکن است قبلاً حذف شده باشد."
        else:
            response_text = "خطا در حذف یادآور. لطفاً دوباره تلاش کنید."
        
        updated_state_dict["current_operation_status"] = None
        if user_profile: # Pass back updated profile if it exists
            updated_state_dict["user_profile"] = user_profile


    elif current_intent == "intent_show_payment_options":
        logger.info(f"handle_intent_node: Showing new payment prompt for user {user_id}")
        chat_id = state.get("chat_id")
        price_tomans = settings.PREMIUM_SUBSCRIPTION_PRICE_TOMANS
        duration_months = settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS
        price_str = f"{to_persian_numerals(f'{price_tomans:,}')} تومان برای {to_persian_numerals(str(duration_months))} ماه"
        from src.payment import create_payment_link
        import asyncio
        amount_rials = price_tomans * 10
        loop = asyncio.get_event_loop()
        success, message, payment_url = await loop.run_in_executor(
            None, create_payment_link, user_id, chat_id, amount_rials
        )
        if success and payment_url:
            payment_prompt_text = (
                "💎 یادآور نامحدود فعال کن!\n\n"
                "با تهیه اشتراک نسخه کامل، دیگه محدودیتی تو تعداد یادآورها نداری و می‌تونی راحت هر چند تا که بخوای ثبت کنی.\n\n"
                f"💰 قیمت: {price_str} \n\n"
                "برای رفتن به درگاه پرداخت روی دکمه زیر بزن 👇"
            )
            payment_keyboard = {
                "type": "InlineKeyboardMarkup",
                "inline_keyboard": [
                    [{"text": "پرداخت و فعال‌سازی", "url": payment_url}]
                ]
            }
            response_text = payment_prompt_text
            response_keyboard_markup = payment_keyboard
        else:
            response_text = f"خطا در ایجاد لینک پرداخت: {message}"
            response_keyboard_markup = None
    # Handling for reminder creation success/cancellation (relies on response_text set by determine_intent or initial block)
    elif current_intent == "intent_create_reminder_confirmed":
        # Response text is likely "تمومه! 🎉..." from earlier logic.
        # current_operation_status was set to "success" if that was the case.
        # This block is mostly for logging or if other "success" scenarios arise.
        logger.info(f"handle_intent_node: Reminder creation confirmed pathway. Final response: '{response_text}'. Status: {current_operation_status}")

    elif current_intent == "intent_create_reminder_cancelled":
        # Response text should be set from determine_intent_node (e.g., "باشه، تنظیمش نکردم...")
        logger.info(f"handle_intent_node: Reminder creation cancelled by user {user_id}. Response: '{response_text}'")

    elif current_intent == "intent_delete_reminder_cancelled":
        # Response text should be set from determine_intent_node
        logger.info(f"handle_intent_node: Reminder deletion cancelled by user {user_id}. Response: '{response_text}'")
        updated_state_dict["current_operation_status"] = None 

    elif current_intent == "unknown_intent":
        # response_text is already set (either specific error from determine_intent or default)
        logger.info(f"handle_intent_node: Handling unknown_intent for user {user_id}. Input: '{state.get('input_text', 'N/A')}'. Response: '{response_text}'")

    # Status-based message overrides and cleanup
    if current_operation_status == "success": # This might be set by various flows
        if "تمومه! 🎉" in response_text: # If it's the generic success from reminder creation
             logger.info(f"handle_intent_node: Reminder creation successful. Response: '{response_text}'")
        # elif current_intent related to payment success would go here if needed
        else: # Other types of success
            # Example: if it was a successful reminder SET but not "تمومه!"
            reminder_details = state.get("reminder_details", {})
            task = reminder_details.get("task", "وظیفه شما")
            utc_dt_str = reminder_details.get("datetime_utc_iso")
            if utc_dt_str:
                utc_dt = datetime.datetime.fromisoformat(utc_dt_str.replace("Z", "+00:00"))
                tehran_dt = utc_dt.astimezone(pytz.timezone('Asia/Tehran'))
                jalali_date_str_display = format_jalali_date(jdatetime.datetime.fromgregorian(datetime=tehran_dt))
                time_str_display = tehran_dt.strftime('%H:%M')
                day_name = get_persian_day_name(tehran_dt.weekday())
                response_text = MSG_REMINDER_SET.format(
                    task=task, 
                    date=f"{day_name}، {jalali_date_str_display}", 
                    time=to_persian_numerals(time_str_display)
                )
            else: # Fallback if datetime is missing but somehow status is success
                response_text = f"یادآور شما برای «{task}» با موفقیت تنظیم شد، اما خطایی در نمایش تاریخ و زمان رخ داد."
        
        # General cleanup for any "success"
        updated_state_dict["current_operation_status"] = None 
        updated_state_dict["reminder_details"] = None # Clear reminder specific context

    elif current_operation_status == "limit_reached_free":
        response_text = settings.MSG_REMINDER_LIMIT_REACHED_FREE.format(limit=settings.MAX_REMINDERS_FREE_TIER)
        limit_exceeded_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [{"text": "یادآور نامحدود 👑", "callback_data": "show_subscription_options"}]
            ]
        }
        response_keyboard_markup = limit_exceeded_keyboard
        updated_state_dict["current_operation_status"] = None

    elif current_operation_status == "limit_reached_premium":
        response_text = settings.MSG_REMINDER_LIMIT_REACHED_PREMIUM.format(limit=settings.MAX_REMINDERS_PREMIUM_TIER)
        updated_state_dict["current_operation_status"] = None

    elif current_operation_status == "error_db":
        response_text = "متاسفانه هنگام ذخیره یادآور شما خطایی در پایگاه داده رخ داد. لطفاً دوباره تلاش کنید."
        updated_state_dict["current_operation_status"] = None
    
    elif current_operation_status == "error_missing_data":
        response_text = "اطلاعات کافی برای ایجاد یادآور (مانند متن یا زمان) دریافت نشد. لطفاً دوباره سعی کنید."
        updated_state_dict["current_operation_status"] = None
    
    elif current_operation_status and "error" in current_operation_status:
        # Catch-all for other specific errors if response_text wasn't set by them
        if not response_text_from_state: # If the erroring node didn't set a specific message
            response_text = f"خطایی رخ داد: {current_operation_status}. لطفاً دوباره تلاش کنید."
        logger.error(f"handle_intent_node: Handling generic error status '{current_operation_status}' for user {user_id}. Response: '{response_text}'")
        updated_state_dict["current_operation_status"] = None


    updated_state_dict["response_text"] = response_text
    if response_keyboard_markup is not None:
        updated_state_dict["response_keyboard_markup"] = response_keyboard_markup
    # else: # No need for else, if None, it won't be in dict or will be None
    #     updated_state_dict["response_keyboard_markup"] = None 

    logger.debug(f"handle_intent_node for user {user_id} returning with response_text: '{str(response_text)[:100]}...', keyboard: {bool(updated_state_dict.get('response_keyboard_markup'))}")
    return updated_state_dict

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
    if intent == "intent_create_zibal_link":
        logger.info("Routing to create_zibal_payment_link_node for payment link creation.")
        return "create_zibal_payment_link_node"
    if intent == "unknown_intent":
        logger.info("Routing to handle_intent_node for unknown_intent (will generate default response).")
        return "handle_intent_node"
    logger.info(f"Routing to handle_intent_node for intent: {intent}")
    return "handle_intent_node"

# --- Payment Node: Create Zibal Payment Link ---
async def create_zibal_payment_link_node(state: AgentState) -> Dict[str, Any]:
    """Node to create a Zibal payment link and send it to the user."""
    logger.info(f"Graph: Entered create_zibal_payment_link_node for user {state.get('user_id')}")
    user_id = state.get("user_id")
    chat_id = state.get("chat_id")
    price_tomans = settings.PREMIUM_SUBSCRIPTION_PRICE_TOMANS
    duration_months = settings.PREMIUM_SUBSCRIPTION_DURATION_MONTHS
    from src.payment import create_payment_link

    # Zibal expects amount in Rials (Tomans * 10)
    amount_rials = price_tomans * 10
    success, message, payment_url = create_payment_link(user_id, chat_id, amount_rials)

    if success and payment_url:
        price_str = f"{to_persian_numerals(f'{price_tomans:,}')} تومان برای {to_persian_numerals(str(duration_months))} ماه"
        response_text = (
            "💎 یادآور نامحدود فعال کن!\n\n"
            "با تهیه اشتراک نسخه کامل، دیگه محدودیتی تو تعداد یادآورها نداری و می‌تونی راحت هر چند تا که بخوای ثبت کنی.\n\n"
            f"💰 قیمت: {price_str} \n\n"
            "برای رفتن به درگاه پرداخت روی دکمه زیر بزن 👇"
        )
        payment_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [{"text": "پرداخت و فعال‌سازی", "url": payment_url}]
            ]
        }
        return {
            "response_text": response_text,
            "response_keyboard_markup": payment_keyboard,
            "current_node_name": "create_zibal_payment_link_node"
        }
    else:
        logger.error(f"Failed to create payment link for user {user_id}: {message}")
        return {
            "response_text": f"خطا در ایجاد لینک پرداخت: {message}",
            "current_node_name": "create_zibal_payment_link_node"
        }