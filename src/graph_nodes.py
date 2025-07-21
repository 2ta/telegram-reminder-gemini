import logging
from typing import Dict, Any, Optional
import json
import google.generativeai as genai
import datetime
import pytz
import urllib.parse
import uuid 
import re
from sqlalchemy import func, or_
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import secrets

from src.graph_state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config.config import settings, MSG_WELCOME, MSG_REMINDER_SET, MSG_LIST_EMPTY_NO_REMINDERS, MSG_PAYMENT_PROMPT, MSG_PAYMENT_BUTTON, MSG_ALREADY_PREMIUM
from src.datetime_utils import parse_english_datetime_to_utc, resolve_english_date_phrase_to_range, format_datetime_for_display
from src.models import Reminder, User, SubscriptionTier
from src.database import get_db
from sqlalchemy.orm import Session
from src.payment import DEFAULT_PAYMENT_AMOUNT
from src.conversation_memory import conversation_memory
from src.langsmith_config import log_graph_execution, create_run_name

# Global cache for pending reminder details before confirmation
PENDING_REMINDER_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger(__name__)

# Helper function to get current English date and time for the LLM prompt
def get_current_english_datetime_for_prompt() -> str:
    try:
        now_utc = datetime.datetime.now(pytz.utc)
        return now_utc.strftime("%A, %B %d, %Y at %I:%M %p UTC")
    except Exception as e:
        logger.error(f"Error generating current English datetime for prompt: {e}", exc_info=True)
        return "Current date and time unavailable"

async def parse_datetime_with_llm(input_text: str, user_timezone: str = "UTC") -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Use Gemini LLM to intelligently parse datetime input and extract date, time, and type.
    
    Args:
        input_text: User input like "Today 10 AM", "tomorrow 3:30 PM", "next Monday", etc.
        user_timezone: User's timezone for context
        
    Returns:
        Tuple of (date_str, time_str, input_type) where:
        - date_str: Extracted date component (can be None)
        - time_str: Extracted time component (can be None) 
        - input_type: "date_only", "time_only", "date_time", "unclear", or "invalid"
    """
    try:
        # Initialize Gemini LLM
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.1,  # Low temperature for consistent parsing
            max_tokens=500
        )
        
        current_datetime = get_current_english_datetime_for_prompt()
        
        prompt = ChatPromptTemplate.from_template("""
You are an expert datetime parser. Your task is to analyze user input and extract date and time components intelligently.

Current datetime: {current_datetime}
User timezone: {user_timezone}

User input: "{input_text}"

Analyze this input and determine:
1. What type of input this is
2. Extract the date component (if any)
3. Extract the time component (if any)

Consider:
- Common misspellings (e.g., "tommorow" = "tomorrow")
- Natural language variations
- Relative dates (today, tomorrow, next week, etc.)
- Time periods (morning, afternoon, evening, etc.)
- 12/24 hour formats
- Various date formats

Respond in this exact JSON format:
{{
    "input_type": "date_only|time_only|date_time|unclear|invalid",
    "date_str": "extracted date or null",
    "time_str": "extracted time or null",
    "confidence": "high|medium|low",
    "reasoning": "brief explanation of your analysis"
}}

Examples:
- Input: "tomorrow 10 AM" → {{"input_type": "date_time", "date_str": "tomorrow", "time_str": "10 AM", "confidence": "high"}}
- Input: "tommorow 3:30 PM" → {{"input_type": "date_time", "date_str": "tomorrow", "time_str": "3:30 PM", "confidence": "high"}}
- Input: "next Monday" → {{"input_type": "date_only", "date_str": "next Monday", "time_str": null, "confidence": "high"}}
- Input: "10 AM" → {{"input_type": "time_only", "date_str": null, "time_str": "10 AM", "confidence": "high"}}
- Input: "morning" → {{"input_type": "time_only", "date_str": null, "time_str": "morning", "confidence": "high"}}
- Input: "asdf" → {{"input_type": "invalid", "date_str": null, "time_str": null, "confidence": "high"}}

Only respond with valid JSON, no other text.
""")
        
        chain = prompt | llm | StrOutputParser()
        
        result = await chain.ainvoke({
            "current_datetime": current_datetime,
            "user_timezone": user_timezone,
            "input_text": input_text
        })
        
        # Parse the JSON response
        try:
            # Handle markdown-wrapped JSON responses
            json_str = result.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]  # Remove ```json
            if json_str.endswith("```"):
                json_str = json_str[:-3]  # Remove ```
            json_str = json_str.strip()
            
            parsed_result = json.loads(json_str)
            date_str = parsed_result.get("date_str")
            time_str = parsed_result.get("time_str")
            input_type = parsed_result.get("input_type", "unclear")
            confidence = parsed_result.get("confidence", "low")
            reasoning = parsed_result.get("reasoning", "")
            
            logger.info(f"LLM datetime parsing: '{input_text}' -> type='{input_type}', date='{date_str}', time='{time_str}', confidence='{confidence}', reasoning='{reasoning}'")
            
            return date_str, time_str, input_type
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {result}, error: {e}")
            return None, None, "unclear"
            
    except Exception as e:
        logger.error(f"Error in LLM datetime parsing for '{input_text}': {e}", exc_info=True)
        return None, None, "unclear"

def split_datetime_input(input_text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Legacy function - kept for backward compatibility.
    Now delegates to the LLM-based parser.
    """
    logger.warning("split_datetime_input is deprecated, use parse_datetime_with_llm instead")
    # For now, return None values to force using the LLM parser
    return None, None

async def entry_node(state: AgentState) -> Dict[str, Any]:
    """Node that processes the initial input and determines message type."""
    user_id = state.get('user_id')
    logger.info(f"Graph: Entered entry_node for user {user_id}")
    current_input = state.get("input_text", "")
    message_type = state.get("message_type", "unknown")
    logger.info(f"Input: '{current_input}', Type: {message_type}")
    
    # Log to LangSmith
    log_graph_execution(user_id, "entry_node", {
        "input_text": current_input,
        "message_type": message_type
    })
    
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

        # For premium users, expiry date is mandatory
        premium_until = None
        if is_premium:
            if not user_db_obj.subscription_expiry:
                logger.error(f"Premium user {user_id} has no subscription expiry date! This is a data integrity issue.")
                return {
                    "user_profile": None,
                    "error_message": f"Premium user {user_id} has no expiry date. Data integrity issue.",
                    "current_node_name": "load_user_profile_node"
                }
            premium_until = user_db_obj.subscription_expiry.isoformat()
        else:
            # Free users don't have expiry dates
            premium_until = None

        user_profile_data = {
            "user_db_id": user_db_obj.id,
            "username": user_db_obj.username,
            "first_name": user_db_obj.first_name,
            "last_name": user_db_obj.last_name,
            "is_premium": is_premium,  # Derived from subscription_tier
            "premium_until": premium_until,
            "language_code": user_db_obj.language_code,
            "timezone": user_db_obj.timezone,  # Add timezone to profile
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
    user_id = state.get('user_id')
    logger.info(f"Graph: Entered determine_intent_node for user {user_id}")
    input_text_raw = state.get("input_text")
    input_text = input_text_raw.strip() if input_text_raw else ""
    message_type = state.get("message_type")
    effective_input = input_text # Assuming callback_data is in input_text for callbacks
    
    # Log to LangSmith
    log_graph_execution(user_id, "determine_intent_node", {
        "input_text": input_text,
        "message_type": message_type
    })
    
    # Check conversation memory for pending clarifications
    chat_id = state.get("chat_id")
    session_id = conversation_memory.get_session_id(user_id, chat_id)
    conversation_context = conversation_memory.get_conversation_context(session_id)
    
    # If we have a pending clarification from conversation memory, treat this input as a response
    if conversation_context["has_pending_clarification"] and input_text:
        pending_clarification_type = conversation_context["pending_clarification_type"]
        
        # Check if the user is sending a complete reminder request instead of just answering the clarification
        # Look for patterns like "remind me to X at Y" or "remind me to X on Y"
        complete_reminder_pattern = re.search(r'remind\s+me\s+to\s+(.+?)\s+(?:at|on|in|by)\s+(.+)', input_text.lower())
        
        if complete_reminder_pattern:
            # User is sending a complete reminder request, ignore the pending clarification
            logger.info(f"User {user_id} sent a complete reminder request, ignoring pending clarification")
            # Clear the conversation memory to treat this as a fresh request
            conversation_memory.clear_conversation_context(session_id)
        else:
            # User is responding to the clarification
            logger.info(f"User {user_id} is responding to pending clarification: {pending_clarification_type}")
            
            # Get the existing reminder context from the conversation memory, as it's the most reliable source.
            reminder_ctx = {
                "collected_task": conversation_context.get("collected_task"),
                "collected_date_str": conversation_context.get("collected_date_str"),
                "collected_time_str": conversation_context.get("collected_time_str"),
                "pending_clarification_type": pending_clarification_type
            }

            # Use LLM to parse the current input
            user_profile = state.get("user_profile", {})
            user_timezone = user_profile.get("timezone", "UTC")
            logger.info(f"Using LLM to parse clarification response: '{input_text}' for context: {reminder_ctx}")
            llm_date_str, llm_time_str, llm_input_type = await parse_datetime_with_llm(input_text, user_timezone)

            # Merge new info with existing context
            if llm_date_str:
                reminder_ctx["collected_date_str"] = llm_date_str
            if llm_time_str:
                reminder_ctx["collected_time_str"] = llm_time_str
            
            logger.info(f"Context after merging LLM parse results: {reminder_ctx}")

            # Now, check if we have everything we need
            if reminder_ctx.get("collected_date_str") and reminder_ctx.get("collected_time_str"):
                logger.info("All parts collected. Ready for processing.")
                reminder_ctx["pending_clarification_type"] = None
                reminder_ctx["status"] = "ready_for_processing"
                
                # Clear conversation memory as we are proceeding
                conversation_memory.clear_conversation_context(session_id)
            elif reminder_ctx.get("collected_date_str"):
                logger.info("Date part collected, asking for time.")
                reminder_ctx["pending_clarification_type"] = "time"
                reminder_ctx["status"] = "clarification_needed_time"
            elif reminder_ctx.get("collected_time_str"):
                logger.info("Time part collected, asking for date.")
                reminder_ctx["pending_clarification_type"] = "date"
                reminder_ctx["status"] = "clarification_needed_date"
            else:
                logger.warning(f"Could not parse the follow-up input '{input_text}'. Re-issuing original clarification.")
                # Let the original pending_clarification_type stand
                reminder_ctx["status"] = f"clarification_needed_{pending_clarification_type}"

            return {
                "current_intent": "intent_create_reminder",
                "extracted_parameters": {
                    "task": reminder_ctx.get("collected_task"), 
                    "date": reminder_ctx.get("collected_date_str"), 
                    "time": reminder_ctx.get("collected_time_str")
                },
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": reminder_ctx
            }

    
    # Check if we have a pending clarification from previous state (fallback)
    reminder_ctx = state.get("reminder_creation_context", {})
    pending_clarification_type = reminder_ctx.get("pending_clarification_type")
    
    # If we have a pending clarification, treat this input as a response to that clarification
    if pending_clarification_type and input_text:
        logger.info(f"User {state.get('user_id')} is responding to pending clarification: {pending_clarification_type}")
        
        if pending_clarification_type == "datetime":
            # User is providing date/time for existing task
            collected_task = reminder_ctx.get("collected_task")
            if collected_task:
                # Use LLM to intelligently parse the datetime input
                user_profile = state.get("user_profile", {})
                user_timezone = user_profile.get("timezone", "UTC")
                
                logger.info(f"Using LLM to parse datetime input: '{input_text}' for task: '{collected_task}'")
                date_str, time_str, input_type = await parse_datetime_with_llm(input_text, user_timezone)
                
                if input_type == "date_time" and date_str and time_str:
                    # Successfully parsed both date and time
                    logger.info(f"LLM parsed '{input_text}' into date='{date_str}', time='{time_str}'")
                    combined_input = f"Remind me to {collected_task} {date_str} {time_str}"
                    
                    reminder_ctx["collected_date_str"] = date_str
                    reminder_ctx["collected_time_str"] = time_str
                    reminder_ctx["pending_clarification_type"] = None
                    reminder_ctx["status"] = "ready_for_processing"
                    
                    return {
                        "current_intent": "intent_create_reminder",
                        "extracted_parameters": {"task": collected_task, "date": date_str, "time": time_str},
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": reminder_ctx,
                        "input_text": combined_input
                    }
                elif input_type == "date_only" and date_str:
                    # Only date was found - ask for time
                    logger.info(f"LLM detected date-only input: '{date_str}', asking for time")
                    reminder_ctx = {
                        "collected_task": collected_task,
                        "collected_date_str": date_str,
                        "collected_time_str": None, # Ensure time is null
                        "pending_clarification_type": "time",
                        "status": "clarification_needed_time"
                    }
                    
                    return {
                        "current_intent": "intent_create_reminder",
                        "extracted_parameters": {"task": collected_task, "date": date_str},
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": reminder_ctx,
                        "input_text": input_text
                    }
                elif input_type == "time_only" and time_str:
                    # Only time was found - ask for date
                    logger.info(f"LLM detected time-only input: '{time_str}', asking for date")
                    reminder_ctx = {
                        "collected_task": collected_task,
                        "collected_date_str": None, # Ensure date is null
                        "collected_time_str": time_str,
                        "pending_clarification_type": "date",
                        "status": "clarification_needed_date"
                    }
                    
                    return {
                        "current_intent": "intent_create_reminder",
                        "extracted_parameters": {"task": collected_task, "time": time_str},
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": reminder_ctx,
                        "input_text": input_text
                    }
                else:
                    # LLM couldn't parse the input clearly - ask for clarification
                    logger.info(f"LLM couldn't parse input clearly: '{input_text}', asking for clarification")
                    reminder_ctx = {
                        "collected_task": collected_task,
                        "collected_date_str": None,
                        "collected_time_str": None,
                        "pending_clarification_type": "datetime",
                        "status": "clarification_needed_datetime"
                    }
                    
                    return {
                        "current_intent": "intent_create_reminder",
                        "extracted_parameters": {"task": collected_task},
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": reminder_ctx,
                        "input_text": input_text
                    }

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
                        "response_text": "This reminder has already been set or has expired.", 
                        "current_node_name": "determine_intent_node"
                    }
                task = retrieved_data.get("task")
                parsed_dt_utc = retrieved_data.get("parsed_dt_utc")
                chat_id_from_cache = retrieved_data.get("chat_id")
                recurrence_rule = retrieved_data.get("recurrence_rule")
                if not (task and parsed_dt_utc and chat_id_from_cache):
                    logger.error(f"Incomplete data from cache for ID {confirmation_id}. Retrieved: {retrieved_data}")
                    return {
                        "current_intent": "unknown_intent", 
                        "response_text": "Error: Confirmation information is incomplete (cache).", 
                        "current_node_name": "determine_intent_node"
                    }
                populated_context = {
                    "collected_task": task,
                    "collected_parsed_datetime_utc": parsed_dt_utc,
                    "chat_id_for_creation": chat_id_from_cache,
                    "collected_recurrence_rule": recurrence_rule
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
                    "response_text": "Error in processing confirmation.", 
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
                        "response_text": "Okay, I didn't set it. ❌ Just tell me again what and when to remind you. 🙂",
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": {}, 
                        "pending_confirmation": None
                    }
                else:
                    logger.warning(f"Confirmation ID {confirmation_id} not found in cache for 'no' callback {effective_input}")
                    return {
                        "current_intent": "unknown_intent",
                        "response_text": "This request has already been cancelled or has expired.",
                        "current_node_name": "determine_intent_node",
                        "reminder_creation_context": {},
                        "pending_confirmation": None
                    }
            except Exception as e:
                logger.error(f"Error cleaning up pending confirmation for ID in '{effective_input}': {e}", exc_info=True)
                return {
                    "current_intent": "unknown_intent",
                    "response_text": "Error in processing cancellation.",
                    "current_node_name": "determine_intent_node",
                    "reminder_creation_context": {},
                    "pending_confirmation": None
                }
        elif effective_input == "confirm_create_reminder:no": # Deprecated branch
            logger.warning(f"DEBUG: Matched DEPRECATED callback for 'confirm_create_reminder:no': {effective_input}. Should include ID.")
            return {
                "current_intent": "intent_create_reminder_cancelled",
                "response_text": "Okay, I didn't set it. ❌ Just tell me again what and when to remind you. 🙂",
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
                return {"current_intent": "unknown_intent", "response_text": "Error in processing delete request.", "current_node_name": "determine_intent_node"}
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
                return {"current_intent": "unknown_intent", "response_text": "Error in processing delete command.", "current_node_name": "determine_intent_node"}
        elif effective_input == "cancel_delete_reminder":
            logger.info(f"DEBUG: Matched callback for 'cancel_delete_reminder'")
            return {
                "current_intent": "intent_delete_reminder_cancelled",
                "response_text": "Okay, I didn't delete it. Your reminder remains active 👍",
                "current_node_name": "determine_intent_node"
            }
        elif effective_input.startswith("view_reminders:page:"):
            try:
                page = int(effective_input.split("view_reminders:page:",1)[1])
                logger.info(f"Detected view_reminders pagination callback for page {page}")
                return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": page}, "current_node_name": "determine_intent_node"}
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing view_reminders pagination callback '{effective_input}': {e}", exc_info=True)
                return {"current_intent": "unknown_intent", "response_text": "Error in processing pagination.", "current_node_name": "determine_intent_node"}
        elif effective_input == "show_subscription_options":
            logger.info(f"Detected 'show_subscription_options' callback.")
            return {"current_intent": "intent_show_payment_options", "current_node_name": "determine_intent_node"}
        elif effective_input == "initiate_payment_stripe":
            logger.info(f"Detected 'initiate_payment_stripe' callback.")
            return {"current_intent": "intent_payment_initiate_stripe", "current_node_name": "determine_intent_node"}

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
                return {"current_intent": "unknown_intent", "response_text": "Invalid delete command format. Please use the delete button next to the reminder.", "current_node_name": "determine_intent_node"}
    
    if input_text == "My Reminders":
        logger.info(f"Detected 'My Reminders' text input from user {state.get('user_id')}")
        return {"current_intent": "intent_view_reminders", "extracted_parameters": {"page": 1}, "current_node_name": "determine_intent_node"}
    elif input_text == "Unlimited Reminders 👑": 
        logger.info(f"Detected 'Unlimited Reminders 👑' text input from user {state.get('user_id')}")
        return {"current_intent": "intent_show_payment_options", "current_node_name": "determine_intent_node"}

    # --- Priority 3: LLM for Potential Reminder Creation (General Text Input) ---
    reminder_ctx = state.get("reminder_creation_context", {})
    pending_clarification = reminder_ctx.get("pending_clarification_type")

    if message_type == "text" or message_type == "voice":
        if pending_clarification:
            logger.info(f"Handling reply to clarification question: {pending_clarification}")
            if pending_clarification == "task":
                reminder_ctx["collected_task"] = effective_input
            elif pending_clarification == "datetime":
                # Assume the input is a date/time string
                reminder_ctx["collected_date_str"] = effective_input
                reminder_ctx["collected_time_str"] = None # Reset time string

            reminder_ctx["pending_clarification_type"] = None # Clear pending clarification
            return {
                "current_intent": "intent_create_reminder",
                "reminder_creation_context": reminder_ctx,
                "current_node_name": "determine_intent_node"
            }

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. LLM NLU will be skipped.")
            # Fall through to unknown_intent at the end
        else:
            try:
                llm = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL_NAME, 
                    temperature=0.3,
                    google_api_key=settings.GEMINI_API_KEY
                )
                current_english_datetime = get_current_english_datetime_for_prompt()
                prompt_template = f"""You are an intelligent assistant for detecting user intent from English text.
Your task is to determine whether the user intends to create a new reminder or not.
If they intend to create a reminder, you should extract the following information:
1.  `task`: The main task that needs to be reminded (e.g., "call my brother", "weekly sales team meeting"). This should not include date and time.
2.  `date_str`: Date-related phrases (e.g., "tomorrow", "day after tomorrow", "next monday", "weekend", "in 3 days", "march 15", "today"). This field can include relative or specific expressions.
3.  `time_str`: Time-related phrases (e.g., "2 pm", "3 in the afternoon", "early morning", "around noon", "11 PM"). This field can include relative or specific expressions.
4.  `recurrence_rule`: Recurring patterns (e.g., "every day", "daily", "weekly", "monthly", "every monday", "every morning"). This should be null for one-time reminders.

IMPORTANT: When the user provides a combined date-time phrase like "11 PM today" or "tomorrow at 2 PM", you should separate them:
- For "11 PM today": date_str="today", time_str="11 PM"
- For "tomorrow at 2 PM": date_str="tomorrow", time_str="2 PM"
- For "next Monday at 9 AM": date_str="next monday", time_str="9 AM"

RECURRING PATTERNS: Look for patterns like:
- "every day at 8 AM" → recurrence_rule="daily", time_str="8 AM", date_str="today"
- "daily reminder" → recurrence_rule="daily", date_str="today"
- "weekly meeting" → recurrence_rule="weekly", date_str="today"
- "monthly check" → recurrence_rule="monthly", date_str="today"
- "every month on the 15th" → recurrence_rule="monthly", time_str="15th", date_str="today"
- "every month at 22nd" → recurrence_rule="monthly", time_str="22nd", date_str="today"
- "every month at 22th" → recurrence_rule="monthly", time_str="22th", date_str="today"
- "every month at 22th at 6:10 PM" → recurrence_rule="monthly", time_str="22th at 6:10 PM", date_str="today" (keep the combined day and time for parsing)
- "every month on the 15th at 3:30 PM" → recurrence_rule="monthly", time_str="3:30 PM", date_str="today"
- "every morning" → recurrence_rule="daily", time_str="morning", date_str="today"
- "every evening" → recurrence_rule="daily", time_str="evening", date_str="today"
- "every night" → recurrence_rule="daily", time_str="night", date_str="today"
- "every afternoon" → recurrence_rule="daily", time_str="afternoon", date_str="today"

IMPORTANT: For recurring reminders, if no specific date is mentioned, use "today" as the date_str to establish the first occurrence.
For monthly reminders, if a day is specified (like "22th", "15th"), extract it as time_str.

Current date and time: {current_english_datetime}

User text: "{input_text}"

Please provide your response only and only in the format of a JSON object with the following structure:
{{
  "is_reminder_creation_intent": boolean,
  "task": "string or null",
  "date_str": "string or null",
  "time_str": "string or null",
  "recurrence_rule": "string or null"
}}

The user may provide only the task. If so, `is_reminder_creation_intent` should be true and the `task` field should be populated.
"""
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
                        recurrence_rule = parsed_llm_response.get("recurrence_rule")
                        # Allow reminder intent if at least a task is present.
                        if task:
                            logger.info(f"LLM determined 'intent_create_reminder'. Task: '{task}', Date: '{date_str}', Time: '{time_str}', Recurrence: '{recurrence_rule}'")
                            return {
                                "current_intent": "intent_create_reminder",
                                "extracted_parameters": {"date": date_str, "time": time_str, "task": task, "recurrence_rule": recurrence_rule},
                                "current_node_name": "determine_intent_node",
                                "reminder_creation_context": {
                                    "collected_task": task,
                                    "collected_date_str": date_str,
                                    "collected_time_str": time_str,
                                    "collected_recurrence_rule": recurrence_rule,
                                    "pending_clarification_type": None
                                }
                            }
                        else:
                            logger.warning(f"LLM indicated reminder intent, but task is missing. LLM Output: {parsed_llm_response}")
                            # Fall through to unknown_intent if task is missing
                    else:
                        logger.info(f"LLM determined 'is_reminder_creation_intent' is false for input: '{input_text}'")
                        # Fall through to unknown_intent
                except json.JSONDecodeError as json_e:
                    logger.error(f"Failed to parse JSON response from LLM: {json_e}. Raw response for user '{state.get('user_id')}': {llm_response_content}")
                    # Fall through to unknown_intent
            except Exception as e:
                logger.error(f"Error during LLM call in determine_intent_node for user '{state.get('user_id')}': {e}", exc_info=True)
                # Fall through to unknown_intent

    # --- Default Fallback (Unknown Intent) ---
    logger.warning(f"Could not determine a specific intent for user '{state.get('user_id')}', input: '{input_text}'. Treating as unknown_intent.")
    current_reminder_creation_context = state.get("reminder_creation_context") if state.get("reminder_creation_context") is not None else {}
    # Using the more specific message for unknown intent when reminder creation is the primary NLU focus now
    unknown_intent_response_text = (
        f"Sorry, I couldn't understand your intent from '{input_text}' for creating a reminder. "
        "Please express your task, date and time more clearly. For example: 'Remind me to call the doctor tomorrow at 10 AM'"
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
                language_code=user_telegram_details.get("language_code"),
                timezone='UTC'  # Default timezone, user will be prompted to change it
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
    time_str = reminder_ctx.get("collected_time_str")

    logger.info(f"process_datetime_node: About to parse date_str='{date_str}', time_str='{time_str}' for user {state.get('user_id')}")
    
    # Only attempt parsing if intent is reminder-related and parameters are present
    if current_intent == "intent_create_reminder": # Or if it's an edit flow later
        # Store recurrence rule if present
        recurrence_rule = reminder_ctx.get("collected_recurrence_rule")
        if recurrence_rule:
            reminder_ctx["collected_recurrence_rule"] = recurrence_rule
            logger.info(f"Recurrence rule detected: '{recurrence_rule}'")
        
        if date_str or time_str:
            logger.info(f"Attempting to parse date='{date_str}', time='{time_str}' for intent '{current_intent}'") # Removed am_pm from log
            try:
                # Get user's timezone from profile
                user_timezone = 'UTC'  # Default fallback
                if state.get("user_profile"):
                    user_timezone = state.get("user_profile").get("timezone", 'UTC')
                
                # Special handling for monthly recurring reminders with day specifications
                if recurrence_rule and recurrence_rule.lower() == "monthly" and time_str:
                    import re
                    import datetime
                    
                    # Check if time_str contains both day and time (like "22th at 6:10 PM")
                    combined_pattern = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+at\s+(.+)", time_str.strip())
                    if combined_pattern:
                        day = int(combined_pattern.group(1))
                        actual_time_str = combined_pattern.group(2)
                        logger.info(f"Extracted day {day} and time '{actual_time_str}' from combined string")
                        
                        if 1 <= day <= 31:
                            # Parse the actual time using a helper function
                            def parse_time_only(time_str: str, user_tz: str) -> datetime.time:
                                """Parse time string and return time object in user's timezone"""
                                import re
                                # Parse time like "6:10 PM", "3:30 AM", etc.
                                time_match = re.match(r"(\d{1,2})(?::(\d{1,2}))?\s*(a\.?m\.?|p\.?m\.?)?", time_str.strip().lower())
                                if time_match:
                                    hour_str = time_match.group(1)
                                    minute_str = time_match.group(2)
                                    period_str = time_match.group(3)
                                    
                                    hour = int(hour_str)
                                    minute = int(minute_str) if minute_str else 0
                                    
                                    if period_str:
                                        period_normalized = period_str.lower().replace('.', '')
                                        if period_normalized == "am" and hour == 12:
                                            hour = 0  # 12 AM
                                        elif period_normalized == "pm" and 1 <= hour < 12:
                                            hour += 12
                                    
                                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                                        return datetime.time(hour, minute)
                                
                                # Fallback to current time
                                now_utc = datetime.datetime.now(datetime.timezone.utc)
                                if user_tz and user_tz != 'UTC':
                                    import pytz
                                    tz_obj = pytz.timezone(user_tz)
                                    now_in_user_tz = now_utc.astimezone(tz_obj)
                                    return now_in_user_tz.time()
                                else:
                                    return now_utc.time()
                            
                            target_time = parse_time_only(actual_time_str, user_timezone)
                            
                            # Create date for the specified day
                            now_utc = datetime.datetime.now(datetime.timezone.utc)
                            current_month = now_utc.month
                            current_year = now_utc.year
                            
                            try:
                                target_date = datetime.date(current_year, current_month, day)
                                # If the date is in the past, move to next month
                                if target_date < now_utc.date():
                                    if current_month == 12:
                                        target_date = datetime.date(current_year + 1, 1, day)
                                    else:
                                        target_date = datetime.date(current_year, current_month + 1, day)
                                
                                # Create datetime in user's timezone
                                if user_timezone and user_timezone != 'UTC':
                                    import pytz
                                    tz_obj = pytz.timezone(user_timezone)
                                    local_dt = datetime.datetime.combine(target_date, target_time)
                                    local_dt_with_tz = tz_obj.localize(local_dt)
                                    parsed_dt_utc = local_dt_with_tz.astimezone(pytz.utc)
                                else:
                                    local_dt = datetime.datetime.combine(target_date, target_time)
                                    parsed_dt_utc = local_dt.replace(tzinfo=datetime.timezone.utc)
                                
                                logger.info(f"Created monthly recurring reminder for day {day} at {target_time} -> {parsed_dt_utc}")
                            except ValueError:
                                logger.warning(f"Invalid day {day} for current month, falling back to regular parsing")
                                parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                        else:
                            parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                    else:
                        # Check if time_str is just a day of the month (like "22th", "15th")
                        day_match = re.match(r"(\d{1,2})(?:st|nd|rd|th)?", time_str.strip())
                        if day_match:
                            day = int(day_match.group(1))
                            if 1 <= day <= 31:
                                # Create a datetime for the current month with the specified day
                                now_utc = datetime.datetime.now(datetime.timezone.utc)
                                current_month = now_utc.month
                                current_year = now_utc.year
                                
                                # Try to create the date, handle invalid dates (like 31st in February)
                                try:
                                    target_date = datetime.date(current_year, current_month, day)
                                    # If the date is in the past, move to next month
                                    if target_date < now_utc.date():
                                        if current_month == 12:
                                            target_date = datetime.date(current_year + 1, 1, day)
                                        else:
                                            target_date = datetime.date(current_year, current_month + 1, day)
                                    
                                    # Use current time for the reminder
                                    target_time = now_utc.time()
                                    local_dt = datetime.datetime.combine(target_date, target_time)
                                    
                                    # Convert to UTC
                                    if user_timezone and user_timezone != 'UTC':
                                        import pytz
                                        tz_obj = pytz.timezone(user_timezone)
                                        local_dt_with_tz = tz_obj.localize(local_dt)
                                        parsed_dt_utc = local_dt_with_tz.astimezone(pytz.utc)
                                    else:
                                        parsed_dt_utc = local_dt.replace(tzinfo=datetime.timezone.utc)
                                    
                                    logger.info(f"Created monthly recurring reminder for day {day} at {parsed_dt_utc}")
                                except ValueError:
                                    # Invalid date (like 31st in February), fall back to regular parsing
                                    logger.warning(f"Invalid day {day} for current month, falling back to regular parsing")
                                    parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                            else:
                                # Invalid day number, fall back to regular parsing
                                parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                        else:
                            # Not a day specification, use regular parsing
                            parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                else:
                    # Regular parsing for non-monthly or non-day-specification cases
                    parsed_dt_utc = parse_english_datetime_to_utc(date_str, time_str, user_timezone)
                
                if parsed_dt_utc:
                    # Ensure for recurring reminders, the first due date is always in the future
                    if recurrence_rule:
                        import pytz
                        now_utc = datetime.datetime.now(pytz.utc)
                        user_tz = pytz.timezone(user_timezone) if user_timezone and user_timezone != 'UTC' else pytz.utc
                        parsed_local = parsed_dt_utc.astimezone(user_tz)
                        now_local = now_utc.astimezone(user_tz)
                        logger.info(f"[REMINDER DEBUG] (ENTRY) Recurring scheduling logic: parsed_dt_utc={parsed_dt_utc}, parsed_local={parsed_local}, now_utc={now_utc}, now_local={now_local}, recurrence_rule={recurrence_rule}")
                        # For recurring reminders, always schedule the first due date in the future
                        while parsed_local <= now_local:
                            logger.info(f"[REMINDER DEBUG] parsed_local ({parsed_local}) <= now_local ({now_local}), bumping to next occurrence for recurrence_rule: {recurrence_rule}")
                            if recurrence_rule.lower() == 'daily':
                                parsed_local = parsed_local + datetime.timedelta(days=1)
                            elif recurrence_rule.lower() == 'weekly':
                                parsed_local = parsed_local + datetime.timedelta(weeks=1)
                            elif recurrence_rule.lower() == 'monthly':
                                month = parsed_local.month + 1
                                year = parsed_local.year
                                if month > 12:
                                    month = 1
                                    year += 1
                                day = min(parsed_local.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
                                try:
                                    parsed_local = parsed_local.replace(year=year, month=month, day=day)
                                except Exception:
                                    parsed_local = parsed_local + datetime.timedelta(days=30)
                            else:
                                break
                        logger.info(f"[REMINDER DEBUG] (EXIT) Final scheduled parsed_local: {parsed_local}, parsed_dt_utc: {parsed_local.astimezone(pytz.utc)}")
                        # Convert back to UTC
                        parsed_dt_utc = parsed_local.astimezone(pytz.utc)
                    logger.info(f"Successfully parsed datetime to UTC: {parsed_dt_utc}")
                    # Store in context for subsequent nodes
                    reminder_ctx["collected_parsed_datetime_utc"] = parsed_dt_utc
                else:
                    logger.warning(f"Failed to parse date/time from strings: date='{date_str}', time='{time_str}'")
                    # If parsing fails, ensure collected_parsed_datetime_utc is None or removed
                    reminder_ctx["collected_parsed_datetime_utc"] = None
                    # Add a flag for failed parsing
                    reminder_ctx["datetime_parse_failed"] = True
            except Exception as e:
                logger.error(f"Error during date/time parsing: {e}", exc_info=True)
                reminder_ctx["collected_parsed_datetime_utc"] = None
                reminder_ctx["datetime_parse_failed"] = True
        else:
            logger.info(f"No date/time strings found in context/params for intent '{current_intent}'")
            reminder_ctx["collected_parsed_datetime_utc"] = None # Ensure it's None
    else:
        logger.info(f"Skipping datetime parsing for intent '{current_intent}'.")
    
    return {
        "reminder_creation_context": reminder_ctx,
        "current_node_name": "process_datetime_node"
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
    datetime_parse_failed = reminder_ctx.get("datetime_parse_failed", False)
    
    # Default to free tier limits if profile is not loaded yet (e.g., new user)
    current_reminder_count = 0
    reminder_limit = settings.MAX_REMINDERS_FREE_TIER
    is_premium = False
    tier_name = "Free" # Default tier name for messaging

    if user_profile: # If profile exists, use its values
        current_reminder_count = user_profile.get("current_reminder_count", 0)
        reminder_limit = user_profile.get("reminder_limit", settings.MAX_REMINDERS_FREE_TIER)
        is_premium = user_profile.get("is_premium", False)
        tier_name = "Premium" if is_premium else "Free"
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
            limit=str(reminder_limit), 
            tier_name=tier_name
        )
        
        limit_exceeded_keyboard = None
        if not is_premium: # Show subscription options button only for non-premium users
            limit_exceeded_keyboard = {
                "type": "InlineKeyboardMarkup",
                "inline_keyboard": [
                    [{"text": "Unlimited Reminders 👑", "callback_data": "show_subscription_options"}]
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

    # --- 2. Check for specific clarification types from determine_intent_node ---
    current_status = reminder_ctx.get("status")
    if current_status == "clarification_needed_date":
        logger.info(f"User {user_id} needs date clarification for task '{collected_task}'")
        pending_clarification_type = "date"
        clarification_question_text = f"What date should I remind you about '{collected_task}'? (e.g., tomorrow, 22 July, next Monday)"
        new_reminder_creation_status = "clarification_needed_date"
    elif current_status == "clarification_needed_time":
        logger.info(f"User {user_id} needs time clarification for task '{collected_task}'")
        pending_clarification_type = "time"
        clarification_question_text = f"What time should I remind you about '{collected_task}'? (e.g., 10 AM, 3:30 PM, morning)"
        new_reminder_creation_status = "clarification_needed_time"
    elif current_status == "clarification_needed_datetime":
        logger.info(f"User {user_id} needs datetime clarification for task '{collected_task}'")
        pending_clarification_type = "datetime"
        clarification_question_text = f"When should I remind you about '{collected_task}'? (e.g., tomorrow at 10 AM, 22 July 3 PM)"
        new_reminder_creation_status = "clarification_needed_datetime"
    # --- 3. Validate Task ---
    elif not collected_task:
        logger.info(f"Validation failed for user {user_id}: Task is missing.")
        pending_clarification_type = "task"
        clarification_question_text = "What would you like to be reminded of?"
        new_reminder_creation_status = "clarification_needed_task"
    # --- 4. Validate Datetime ---
    elif not collected_parsed_dt_utc:
        if datetime_parse_failed:
            logger.warning(f"Date/time parsing failed for user {user_id}, task '{collected_task}'. Informing user.")
            pending_clarification_type = "datetime"
            clarification_question_text = (
                f"Sorry, I couldn't understand the date and time you provided. "
                f"Please try a different format, e.g., 'tomorrow at 1 PM' or '2024-06-10 13:00'."
            )
            new_reminder_creation_status = "clarification_needed_datetime"
        else:
            logger.info(f"Validation failed for user {user_id}, task '{collected_task}': Datetime is missing or unparseable.")
            pending_clarification_type = "datetime"
            clarification_question_text = f"When should I remind you about '{collected_task}'?"
            new_reminder_creation_status = "clarification_needed_datetime"

    # (Future AM/PM specific clarification check - assuming parse_english_datetime_to_utc handles am_pm_choice or returns None if it's ambiguous and choice is missing)
    # For instance, if parse_english_datetime_to_utc returned a specific error or flag for AM/PM:
    # elif reminder_ctx.get("datetime_parse_requires_ampm_clarification"):
    #     logger.info(f"Validation for user {user_id}, task '{collected_task}': AM/PM clarification needed.")
    #     pending_clarification_type = "am_pm"
    #     ambiguous_hour = reminder_ctx.get("ambiguous_time_details", {}).get("hour", "target time")
    #     clarification_question_text = f"Is {ambiguous_hour} AM or PM?"
    #     clarification_keyboard_markup = {
    #         "type": "InlineKeyboardMarkup",
    #         "inline_keyboard": [
    #             [{"text": "☀️ AM", "callback_data": "clarify_am_pm:am"}, {"text": "🌙 PM", "callback_data": "clarify_am_pm:pm"}]
    #         ]}
    #     new_reminder_creation_status = "clarification_needed_am_pm"
    #     # Ensure determine_intent_node handles "clarify_am_pm:am/pm" callbacks and sets "collected_am_pm_choice"

    elif reminder_ctx.get("status") == "ready_for_processing":
        # This is a follow-up response that has been combined, re-validate
        logger.info(f"Re-validating combined input for user {user_id}: Task='{collected_task}', Datetime='{collected_parsed_dt_utc}'")
        if collected_task and collected_parsed_dt_utc:
            new_reminder_creation_status = "ready_for_confirmation"
        else:
            # Still missing something, ask for clarification
            if not collected_task:
                pending_clarification_type = "task"
                clarification_question_text = "What would you like to be reminded of?"
                new_reminder_creation_status = "clarification_needed_task"
            elif not collected_parsed_dt_utc:
                pending_clarification_type = "datetime"
                clarification_question_text = f"When should I remind you about '{collected_task}'?"
                new_reminder_creation_status = "clarification_needed_datetime"
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
            "response_text": "Error: Reminder information for confirmation is incomplete. Please try again.",
            "current_node_name": "confirm_reminder_details_node",
            "pending_confirmation": None # Ensure this is cleared
        }

    task = reminder_context["collected_task"]
    parsed_dt_utc_val = reminder_context["collected_parsed_datetime_utc"]
    recurrence_rule = reminder_context.get("collected_recurrence_rule")

    # Fix: handle both str and datetime types, use only top-level import
    if isinstance(parsed_dt_utc_val, str):
        try:
            parsed_dt_utc = datetime.datetime.fromisoformat(parsed_dt_utc_val.replace("Z", "+00:00"))
        except Exception as e:
            logger.error(f"Invalid datetime string in reminder_creation_context: {parsed_dt_utc_val}. Error: {e}")
            return {
                "response_text": "Error: The date and time format sent for confirmation is invalid.",
                "current_node_name": "confirm_reminder_details_node",
                "pending_confirmation": None
            }
    elif isinstance(parsed_dt_utc_val, datetime.datetime):
        parsed_dt_utc = parsed_dt_utc_val
    else:
        logger.error(f"Missing or invalid type for datetime in reminder_creation_context: {parsed_dt_utc_val} (type: {type(parsed_dt_utc_val)})")
        return {
            "response_text": "Error: Reminder date and time for confirmation not found.",
            "current_node_name": "confirm_reminder_details_node",
            "pending_confirmation": None
        }

    # Format datetime for display in English (convert from UTC to user's timezone)
    user_timezone = 'UTC'  # Default fallback
    if state.get("user_profile"):
        user_timezone = state.get("user_profile").get("timezone", 'UTC')
    formatted_date_time = format_datetime_for_display(parsed_dt_utc, user_timezone)

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
        "chat_id": chat_id, # Store chat_id
        "recurrence_rule": recurrence_rule # Store recurrence rule if present
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
    
    # Format time display based on whether it's recurring
    if recurrence_rule:
        # For recurring reminders, show the pattern instead of specific date
        if recurrence_rule.lower() == "daily":
            time_display = f"Every day at {formatted_date_time.split(' at ')[1] if ' at ' in formatted_date_time else formatted_date_time}"
        elif recurrence_rule.lower() == "weekly":
            time_display = f"Every week on {formatted_date_time.split(',')[0] if ',' in formatted_date_time else 'the same day'} at {formatted_date_time.split(' at ')[1] if ' at ' in formatted_date_time else formatted_date_time}"
        elif recurrence_rule.lower() == "monthly":
            # Extract day with proper ordinal suffix
            if ',' in formatted_date_time and len(formatted_date_time.split(',')) > 1:
                day_part = formatted_date_time.split(',')[1].strip().split()[1]
                # Add ordinal suffix if not already present
                if not day_part.endswith(('st', 'nd', 'rd', 'th')):
                    day_num = int(day_part)
                    if day_num == 1:
                        day_part = f"{day_num}st"
                    elif day_num == 2:
                        day_part = f"{day_num}nd"
                    elif day_num == 3:
                        day_part = f"{day_num}rd"
                    elif day_num in [11, 12, 13]:
                        day_part = f"{day_num}th"
                    elif day_num % 10 == 1:
                        day_part = f"{day_num}st"
                    elif day_num % 10 == 2:
                        day_part = f"{day_num}nd"
                    elif day_num % 10 == 3:
                        day_part = f"{day_num}rd"
                    else:
                        day_part = f"{day_num}th"
                time_display = f"Every month on the {day_part} at {formatted_date_time.split(' at ')[1] if ' at ' in formatted_date_time else formatted_date_time}"
            else:
                time_display = f"Every month on the same day at {formatted_date_time.split(' at ')[1] if ' at ' in formatted_date_time else formatted_date_time}"
        else:
            time_display = f"Recurring ({recurrence_rule}) at {formatted_date_time.split(' at ')[1] if ' at ' in formatted_date_time else formatted_date_time}"
    else:
        time_display = formatted_date_time
    
    response_text = (
        "Should I set this reminder? 👇\n\n"
        f"📝 Task: {task}\n"
        f"⏰ Time: {time_display}\n\n"
        "If it's correct, click 'Set'\n"
        "If it needs changes, click 'Cancel' and send the new reminder again 🙂"
    )
    
    # Confirmation message keyboard (styled as in the image, using dict format for compatibility)
    keyboard_markup = {
        "type": "InlineKeyboardMarkup",
        "inline_keyboard": [
            [
                {"text": "✅ Set", "callback_data": f"confirm_create_reminder:yes:id={confirmation_id}"},
                {"text": "❌ Cancel", "callback_data": f"confirm_create_reminder:no:id={confirmation_id}"}
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
                    "response_text": "Error: Invalid datetime format in context.",
                    "current_node_name": "create_reminder_node",
                    "reminder_creation_context": reminder_ctx,
                    "pending_confirmation": None
                }
        logger.error(f"Invalid datetime in context for user {user_id}. Task: {task}, DT: {parsed_dt_utc_from_ctx} (type: {type(parsed_dt_utc_from_ctx)}) ")
        return {
            "current_operation_status": "error_missing_details", # MODIFIED KEY
            "response_text": "Error: Missing details for reminder creation.",
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
            "response_text": "Error: Missing details for reminder creation.",
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
                return {"current_operation_status": "error_user_not_found", "response_text": "Error: User not found for reminder creation.", "current_node_name": "create_reminder_node", "pending_confirmation": None} # MODIFIED KEY
        finally:
            db_temp.close()
    
    user_db_id = user_profile.get("user_db_id")
    if not user_db_id: # Should not happen if above logic works
        logger.error(f"Critical: user_db_id still missing for user {user_id} before DB operation.")
        return {"current_operation_status": "error_internal_user_id_missing", "response_text": "Error: Internal user ID missing.", "current_node_name": "create_reminder_node", "pending_confirmation": None} # MODIFIED KEY


    # Reminder Limit Check (re-check here as a safeguard, though validate_and_clarify should handle it)
    # This requires a full user_profile, so if it was minimally reloaded, this check might be less effective
    # or might need to fetch counts again. For simplicity, we assume validate_and_clarify_node did its job.

    db: Session = next(get_db())
    try:
        # Format for database storage (using UTC)
        date_str = parsed_dt_utc.strftime("%Y-%m-%d")
        time_str = parsed_dt_utc.strftime("%H:%M")
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
        recurrence_rule = reminder_ctx.get("collected_recurrence_rule")
        
        new_reminder = Reminder(
            user_id=user_db_id,  # Use the user's actual DB ID
            task=task,
            date_str=date_str,  # Store as regular date string
            time_str=time_str,
            due_datetime_utc=parsed_dt_utc,  # Store the UTC datetime for notifications
            recurrence_rule=recurrence_rule,  # Store recurrence rule if present
            is_active=True
        )
        db.add(new_reminder)
        db.commit()
        db.refresh(new_reminder)
        logger.info(f"Reminder created successfully for user_db_id {user_db_id} (Telegram user {user_id}), task: '{task}', due_datetime_utc: {parsed_dt_utc}")
        # Update user_profile's reminder count if profile is fully available
        if user_profile and "current_reminder_count" in user_profile:
            user_profile["current_reminder_count"] += 1
        
        # Format success message in English (convert from UTC to user's timezone)
        user_timezone = 'UTC'  # Default fallback
        if user_profile:
            user_timezone = user_profile.get("timezone", 'UTC')
        formatted_datetime = format_datetime_for_display(parsed_dt_utc, user_timezone)
        
        # Format message based on whether it's recurring
        if recurrence_rule:
            if recurrence_rule.lower() == "daily":
                time_display = f"every day at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
            elif recurrence_rule.lower() == "weekly":
                time_display = f"every week on {formatted_datetime.split(',')[0] if ',' in formatted_datetime else 'the same day'} at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
            elif recurrence_rule.lower() == "monthly":
                # Extract day with proper ordinal suffix
                if ',' in formatted_datetime and len(formatted_datetime.split(',')) > 1:
                    day_part = formatted_datetime.split(',')[1].strip().split()[1]
                    # Add ordinal suffix if not already present
                    if not day_part.endswith(('st', 'nd', 'rd', 'th')):
                        day_num = int(day_part)
                        if day_num == 1:
                            day_part = f"{day_num}st"
                        elif day_num == 2:
                            day_part = f"{day_num}nd"
                        elif day_num == 3:
                            day_part = f"{day_num}rd"
                        elif day_num in [11, 12, 13]:
                            day_part = f"{day_num}th"
                        elif day_num % 10 == 1:
                            day_part = f"{day_num}st"
                        elif day_num % 10 == 2:
                            day_part = f"{day_num}nd"
                        elif day_num % 10 == 3:
                            day_part = f"{day_num}rd"
                        else:
                            day_part = f"{day_num}th"
                    time_display = f"every month on the {day_part} at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                else:
                    time_display = f"every month on the same day at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
            else:
                time_display = f"recurring ({recurrence_rule}) at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
            
            response_message = (
                "Done! 🎉\n"
                f"Your recurring reminder has been set for {time_display} and I'll notify you on time 🔔"
            )
        else:
            response_message = (
                "Done! 🎉\n"
                "Your reminder has been set successfully and I'll notify you on time 🔔"
            )
        
        logger.info(f"Reminder successfully set. Task: {task}, Time: {formatted_datetime}")
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
            "response_text": "Sorry, an error occurred while creating your reminder in the database.",
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
            "response_text": "Error: Reminder ID for delete confirmation is not specified.",
            "current_node_name": "confirm_delete_reminder_node"
        }

    db: Session = next(get_db())
    try:
        user_db_id = state.get("user_profile", {}).get("user_db_id")
        if not user_db_id:
            logger.error(f"confirm_delete_reminder_node: user_db_id not found in profile for user {user_id}")
            return {"response_text": "Error: User information for delete confirmation not found.", "current_node_name": "confirm_delete_reminder_node"}

        reminder = db.query(Reminder).filter(
            Reminder.id == reminder_id_to_confirm,
            Reminder.user_id == user_db_id,
            Reminder.is_active == True 
        ).first()

        if not reminder:
            logger.warning(f"confirm_delete_reminder_node: Reminder ID {reminder_id_to_confirm} not found, not active, or doesn't belong to user {user_id}.")
            return {
                "response_text": "The specified reminder for deletion was not found or has already been deleted.",
                "current_node_name": "confirm_delete_reminder_node"
            }

        # Format reminder details for confirmation message
        task_preview = reminder.task[:50] + "..." if len(reminder.task) > 50 else reminder.task
        try:
            gregorian_dt = reminder.gregorian_datetime
            if not gregorian_dt:
                formatted_datetime = "[Date unavailable]"
            else:
                formatted_datetime = format_datetime_for_display(gregorian_dt)
        except Exception as e:
            logger.error(f"Error formatting date for reminder {reminder.id} in confirm_delete: {e}")
            formatted_datetime = "[Error displaying date]"

        confirmation_message = (
            f"⚠️ Are you sure you want to delete this reminder?\n\n"
            f"📝 **Reminder**: {task_preview}\n"
            f"⏰ **Time**: {formatted_datetime}"
        )
        
        confirmation_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [
                    {"text": "Yes, delete ✅", "callback_data": f"execute_delete_reminder:{reminder.id}"},
                    {"text": "No, cancel ❌", "callback_data": "cancel_delete_reminder"}
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
            "response_text": "An error occurred while preparing the delete confirmation message. Please try again.",
            "current_node_name": "confirm_delete_reminder_node"
        }
    finally:
        db.close()

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Handles the determined intent, e.g., fetching reminders, preparing help message."""
    current_intent = state.get("current_intent")
    user_id = state.get("user_id")
    user_profile = state.get("user_profile")
    extracted_parameters = state.get("extracted_parameters", {})
    current_operation_status = state.get("current_operation_status") 
    logger.info(f"Graph: Entered handle_intent_node for user {user_id}, intent: {current_intent}, params: {extracted_parameters}, status: {current_operation_status}")

    # Default response text - updated to remove /help
    default_response_text = "I didn't understand what you asked me to do. Please be more specific."
    
    # Try to get response_text from the state, which might have been set by a previous node (like create_reminder_node)
    response_text_from_state = state.get("response_text")

    if current_intent == "intent_create_reminder_confirmed" and response_text_from_state and "Done! 🎉" in response_text_from_state:
        # If create_reminder_node ran, was successful (implied by "Done!"), and set this response_text, use it.
        # This is a workaround because current_operation_status is not propagating correctly.
        response_text = response_text_from_state
        logger.info(f"Using pre-set success response_text from state for intent_create_reminder_confirmed: {response_text}")
        # Since we're handling this specific success case here, ensure context is cleared as if status was 'success'
        current_operation_status = "success" # Simulate that status was received for subsequent cleanup
    elif current_intent == "intent_create_reminder_cancelled":
        # This intent's response_text is set directly in determine_intent_node
        response_text = response_text_from_state or default_response_text # Fallback just in case
    else:
        response_text = default_response_text
    
    response_keyboard_markup = state.get("response_keyboard_markup") 
    
    updated_state_dict = {"current_node_name": "handle_intent_node"}

    if current_operation_status == "clarification_needed_time":
        task = extracted_parameters.get('task', 'your task')
        response_text = f"What time should I remind you about '{task}'? (e.g., 10 AM, 3:30 PM, morning)"
        logger.info(f"handle_intent_node: Asking for time clarification for user {user_id}, task: '{task}'")
        # Save context to conversation memory
        session_id = conversation_memory.get_session_id(user_id, state.get("chat_id"))
        conversation_memory.add_ai_message(session_id, response_text)

    elif current_operation_status == "clarification_needed_date":
        task = extracted_parameters.get('task', 'your task')
        response_text = f"What date should I remind you about '{task}'? (e.g., tomorrow, 22 July, next Monday)"
        logger.info(f"handle_intent_node: Asking for date clarification for user {user_id}, task: '{task}'")
        # Save context to conversation memory
        session_id = conversation_memory.get_session_id(user_id, state.get("chat_id"))
        conversation_memory.add_ai_message(session_id, response_text)

    elif current_intent == "intent_start":
        response_text = MSG_WELCOME 
        response_keyboard_markup = None
        logger.info(f"handle_intent_node processing intent_start for user {user_id}. MSG_WELCOME will be used.")
        
    elif current_intent == "intent_view_reminders":
        # ... (existing view reminders logic remains the same)
        logger.info(f"handle_intent_node: Preparing to view reminders for user {user_id}.")
        db: Session = next(get_db())
        try:
            if not user_profile or not user_profile.get("user_db_id"):
                logger.warning(f"User profile or user_db_id not found for user {user_id} when viewing reminders.")
                response_text = "Your user information was not found. Please try again."
            else:
                user_db_id = user_profile["user_db_id"]
                page = extracted_parameters.get("page", 1)
                page_size = settings.REMINDERS_PER_PAGE
                offset = (page - 1) * page_size
                logger.info(f"User {user_id}: Preparing to query reminders. user_db_id={user_db_id}, page={page}, page_size={page_size}, offset={offset}")
                reminders_query = db.query(Reminder).filter(
                    Reminder.user_id == user_db_id,
                    Reminder.is_active == True
                ).order_by(Reminder.due_datetime_utc.asc())
                logger.info(f"User {user_id}: reminders_query object created.")
                total_reminders_count = reminders_query.count()
                logger.info(f"User {user_id}: Total reminders count = {total_reminders_count}")
                reminders = reminders_query.offset(offset).limit(page_size).all()
                logger.info(f"User {user_id}: Fetched reminders list (length {len(reminders)})")
                if not reminders and total_reminders_count == 0:
                    logger.info(f"User {user_id}: No reminders found. Using MSG_LIST_EMPTY_NO_REMINDERS.")
                    response_text = MSG_LIST_EMPTY_NO_REMINDERS
                    response_keyboard_markup = None
                elif not reminders and total_reminders_count > 0:
                    logger.info(f"User {user_id}: Reminders exist, but current page {page} is empty.")
                    response_text = f"Page {page} is empty. Go back to the previous page."
                    buttons = []
                    if page > 1:
                        buttons.append([{"text": "Previous Page ⬅️", "callback_data": f"view_reminders:page:{page-1}"}])
                    response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": buttons} if buttons else None
                else:
                    reminder_list_items_text = []
                    action_buttons = [] # For delete buttons
                    reminder_list_header = f"Your active reminders (page {page} of {((total_reminders_count + page_size - 1) // page_size)}):\n\n"
                    for i, reminder in enumerate(reminders):
                        try:
                            gregorian_dt = reminder.gregorian_datetime
                            if not gregorian_dt:
                                logger.warning(f"Could not get datetime for reminder ID {reminder.id}. Skipping display. date_str={reminder.date_str}, time_str={reminder.time_str}, due_datetime_utc={reminder.due_datetime_utc}")
                                reminder_list_items_text.append(f"⚠️ Date and time information for reminder ID {reminder.id} is invalid.")
                                continue
                            # Get user's timezone for proper display
                            user_timezone = 'UTC'  # Default fallback
                            if user_profile:
                                user_timezone = user_profile.get("timezone", 'UTC')
                            formatted_datetime = format_datetime_for_display(gregorian_dt, user_timezone)
                            task_preview = reminder.task[:40] + "..." if len(reminder.task) > 40 else reminder.task
                            
                            # Format display based on whether it's recurring
                            if reminder.recurrence_rule:
                                if reminder.recurrence_rule.lower() == "daily":
                                    time_display = f"🔄 Every day at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                                elif reminder.recurrence_rule.lower() == "weekly":
                                    time_display = f"🔄 Every week on {formatted_datetime.split(',')[0] if ',' in formatted_datetime else 'the same day'} at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                                elif reminder.recurrence_rule.lower() == "monthly":
                                    # Extract day with proper ordinal suffix
                                    if ',' in formatted_datetime and len(formatted_datetime.split(',')) > 1:
                                        day_part = formatted_datetime.split(',')[1].strip().split()[1]
                                        # Add ordinal suffix if not already present
                                        if not day_part.endswith(('st', 'nd', 'rd', 'th')):
                                            day_num = int(day_part)
                                            if day_num == 1:
                                                day_part = f"{day_num}st"
                                            elif day_num == 2:
                                                day_part = f"{day_num}nd"
                                            elif day_num == 3:
                                                day_part = f"{day_num}rd"
                                            else:
                                                day_part = f"{day_num}th"
                                        time_display = f"🔄 Every month on the {day_part} at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                                    else:
                                        time_display = f"🔄 Every month on the same day at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                                else:
                                    time_display = f"🔄 Recurring ({reminder.recurrence_rule}) at {formatted_datetime.split(' at ')[1] if ' at ' in formatted_datetime else formatted_datetime}"
                            else:
                                time_display = f"⏰ {formatted_datetime}"
                            
                            # Add special formatting for recurring reminders
                            if reminder.recurrence_rule:
                                reminder_item_text = (
                                    f"🔄 **{reminder.task}** *(Recurring)*\n"
                                    f"{time_display}"
                                )
                            else:
                                reminder_item_text = (
                                    f"📝 **{reminder.task}**\n"
                                    f"{time_display}"
                                )
                            reminder_list_items_text.append(reminder_item_text)
                            # Add a delete button for each reminder
                            action_buttons.append([
                                {"text": f"Delete reminder: «{task_preview}» 🗑️", "callback_data": f"confirm_delete_reminder:{reminder.id}"}
                            ])
                        except Exception as e:
                            logger.error(f"Error formatting reminder ID {reminder.id} for display: {e}. Raw values: date_str={getattr(reminder, 'date_str', None)}, time_str={getattr(reminder, 'time_str', None)}, due_datetime_utc={getattr(reminder, 'due_datetime_utc', None)}", exc_info=True)
                            reminder_list_items_text.append(f"⚠️ Display error for reminder ID {reminder.id}")
                    response_text = reminder_list_header + "\n\n--------------------\n\n".join(reminder_list_items_text)
                    if not reminder_list_items_text:
                        response_text = reminder_list_header + "No items to display on this page."
                    # Pagination buttons
                    pagination_row = []
                    if page > 1:
                        pagination_row.append({"text": "Previous Page ⬅️", "callback_data": f"view_reminders:page:{page-1}"})
                    if total_reminders_count > page * page_size:
                        pagination_row.append({"text": "➡️ Next Page", "callback_data": f"view_reminders:page:{page+1}"})
                    if pagination_row:
                        action_buttons.append(pagination_row)
                    if action_buttons:
                        response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": action_buttons}
                    else:
                        response_keyboard_markup = None
        except Exception as e:
            logger.error(f"Error fetching reminders for user {user_id}: {e}", exc_info=True)
            response_text = "Error retrieving reminder list. Please try again."
        finally:
            db.close()

    elif current_intent == "intent_delete_reminder" or current_intent == "intent_delete_reminder_confirmed":
        reminder_id_to_delete = None
        if current_intent == "intent_delete_reminder": # from /del_ command
            reminder_id_to_delete = extracted_parameters.get("reminder_id") 
        elif current_intent == "intent_delete_reminder_confirmed": # from confirmation callback
            reminder_id_to_delete = extracted_parameters.get("reminder_id_to_delete")
            logger.info(f"handle_intent_node: Processing confirmed deletion for reminder ID {reminder_id_to_delete} from callback for user {user_id}.")

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
                        reminder_to_delete.updated_at = datetime.datetime.now(pytz.utc)
                        db.commit()
                        delete_status = "deleted"
                        logger.info(f"Reminder ID {reminder_id_to_delete} marked as inactive for user {user_id}.")
                        if user_profile["current_reminder_count"] > 0:
                             user_profile["current_reminder_count"] -=1
                    else:
                        delete_status = "already_inactive"
                        logger.info(f"Reminder ID {reminder_id_to_delete} was already inactive for user {user_id}.")
                else:
                    delete_status = "not_found"
                    logger.warning(f"Reminder ID {reminder_id_to_delete} not found for user {user_id} to delete.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting reminder {reminder_id_to_delete} for user {user_id}: {e}", exc_info=True)
                delete_status = "error"
            finally:
                db.close()
        else:
            logger.warning(f"Cannot delete reminder: Missing reminder_id, user_profile, or user_db_id for user {user_id}.")
            delete_status = "error_missing_info"

        if delete_status == "deleted":
            response_text = f"Reminder '{deleted_task_name}' has been successfully deleted. ✅"
            response_keyboard_markup = None 
        elif delete_status == "already_inactive":
            response_text = "This reminder was already inactive."
        elif delete_status == "not_found":
            response_text = "Reminder not found. It may have been deleted already."
        else: 
            response_text = "Error deleting reminder. Please try again."
        
        logger.info(f"handle_intent_node: Delete reminder status for user {user_id}, reminder ID {reminder_id_to_delete}: {delete_status}")
        updated_state_dict["current_operation_status"] = None # Clear status after handling delete

    # This elif block for intent_create_reminder_confirmed can be simplified or removed
    # as the response_text is now handled by the logic at the beginning of the function
    # if the "تمومه! 🎉" message was found in the state.
    elif current_intent == "intent_create_reminder_confirmed":
        # If we are here, it means the "تمومه! 🎉" message was NOT in response_text_from_state OR this logic path is still hit.
        # This log helps understand if this branch is taken even with the workaround.
        logger.info(f"handle_intent_node: In 'intent_create_reminder_confirmed' block. Current response_text: '{response_text}'. Status: {current_operation_status}")
        # The main success message is now handled by the initial check.
        # If status somehow became "success" but the message wasn't "تمومه! 🎉", this branch might be hit.

    elif current_intent == "intent_create_reminder_cancelled":
        # The response_text for this was already set at the beginning of the function
        # from response_text_from_state, which determine_intent_node had set.
        logger.info(f"handle_intent_node: Reminder creation cancelled by user {user_id}. Response: '{response_text}'")

    elif current_intent == "intent_delete_reminder_cancelled":
        # Response text is set by determine_intent_node for this case.
        # We just need to ensure it's passed through.
        response_text = response_text_from_state or "Delete operation was cancelled."
        logger.info(f"handle_intent_node: Reminder deletion cancelled by user {user_id}. Response: '{response_text}'")
        updated_state_dict["current_operation_status"] = None # Clear any related status

    elif current_intent == "intent_create_reminder":
        # Handle reminder creation intent with clarification needs
        reminder_ctx = state.get("reminder_creation_context", {})
        clarification_status = reminder_ctx.get("status")
        
        if clarification_status == "clarification_needed_datetime":
            # Ask for missing date/time
            task = reminder_ctx.get("collected_task", "this task")
            response_text = f"Certainly. When should I remind you about '{task}'?"
            response_keyboard_markup = None
            logger.info(f"handle_intent_node: Asking for datetime clarification for user {user_id}, task: '{task}'")
            
            # Save to conversation memory
            chat_id = state.get("chat_id")
            session_id = conversation_memory.get_session_id(user_id, chat_id)
            conversation_memory.add_ai_message(session_id, response_text)
            
        elif clarification_status == "clarification_needed_task":
            # Ask for missing task
            response_text = "What would you like to be reminded of?"
            response_keyboard_markup = None
            logger.info(f"handle_intent_node: Asking for task clarification for user {user_id}")
            
            # Save to conversation memory
            chat_id = state.get("chat_id")
            session_id = conversation_memory.get_session_id(user_id, chat_id)
            conversation_memory.add_ai_message(session_id, response_text)
            
        elif clarification_status == "ready_for_confirmation":
            # This should be handled by confirm_reminder_details_node, but fallback here
            response_text = "Ready to confirm reminder details."
            response_keyboard_markup = None
            logger.info(f"handle_intent_node: Reminder ready for confirmation for user {user_id}")
            
        else:
            # Fallback for unknown clarification status
            response_text = "I need more information to create your reminder. Please provide the task and when you'd like to be reminded."
            response_keyboard_markup = None
            logger.warning(f"handle_intent_node: Unknown clarification status '{clarification_status}' for user {user_id}")
            
    elif current_intent == "unknown_intent":
        if response_text_from_state and response_text == default_response_text : # If determine_intent_node already set a specific error
             response_text = response_text_from_state
        else: # Ensure our new default_response_text is used if no specific error was set by determine_intent_node
            response_text = default_response_text

        logger.info(f"handle_intent_node: Handling unknown_intent for user {user_id}. Input was: '{state.get('input_text', 'N/A')}'. Response: '{response_text}'")

    elif current_intent == "intent_show_payment_options":
        logger.info(f"handle_intent_node: Showing payment options for user {user_id}")
        
        # Check if user already has premium
        if user_profile and user_profile.get("is_premium", False):
            # User already has premium - expiry date is mandatory for premium users
            expiry_date = user_profile.get("premium_until")
            if not expiry_date:
                logger.error(f"Premium user {user_id} has no expiry date! This should not happen.")
                response_text = "Sorry, there was an error retrieving your premium subscription details. Please contact support."
                response_keyboard_markup = None
            else:
                # Format the expiry date for display
                if isinstance(expiry_date, str):
                    try:
                        expiry_date = datetime.datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
                    except ValueError:
                        logger.error(f"Invalid expiry date format for premium user {user_id}: {expiry_date}")
                        response_text = "Sorry, there was an error retrieving your premium subscription details. Please contact support."
                        response_keyboard_markup = None
                    else:
                        formatted_expiry = format_datetime_for_display(expiry_date)
                        response_text = MSG_ALREADY_PREMIUM.format(expiry_date=formatted_expiry)
                        response_keyboard_markup = None
                else:
                    # expiry_date is already a datetime object
                    formatted_expiry = format_datetime_for_display(expiry_date)
                    response_text = MSG_ALREADY_PREMIUM.format(expiry_date=formatted_expiry)
                    response_keyboard_markup = None
            
            logger.info(f"handle_intent_node: User {user_id} already has premium, showing premium status message")
        else:
            # User doesn't have premium, show payment options
            amount_usd = DEFAULT_PAYMENT_AMOUNT / 100  # Convert cents to dollars
            response_text = MSG_PAYMENT_PROMPT.format(amount=f"${amount_usd:.2f}")
            payment_keyboard = {
                "type": "InlineKeyboardMarkup",
                "inline_keyboard": [
                    [{"text": MSG_PAYMENT_BUTTON, "callback_data": "initiate_payment_stripe"}]
                ]
            }
            response_keyboard_markup = payment_keyboard

    elif current_intent == "intent_payment_initiate_stripe":
        logger.info(f"handle_intent_node: Initiating Stripe payment for user {user_id}")
        from src.payment import create_payment_link
        
        user_profile = state.get("user_profile", {})
        chat_id = state.get("chat_id", user_id)  # fallback to user_id if chat_id not available
        
        try:
            success, message, payment_url = create_payment_link(user_id, chat_id, DEFAULT_PAYMENT_AMOUNT)
            
            if success and payment_url:
                response_text = f"Great! Click the button below to complete your payment:\n\n💳 Amount: ${DEFAULT_PAYMENT_AMOUNT/100:.2f}"
                payment_keyboard = {
                    "type": "InlineKeyboardMarkup", 
                    "inline_keyboard": [
                        [{"text": "💳 Pay Now", "url": payment_url}]
                    ]
                }
                response_keyboard_markup = payment_keyboard
                logger.info(f"Stripe payment link created for user {user_id}: {payment_url}")
            else:
                response_text = f"Sorry, there was an issue creating the payment link: {message}"
                logger.error(f"Failed to create Stripe payment link for user {user_id}: {message}")
                
        except Exception as e:
            response_text = "Sorry, there was a technical error processing your payment request. Please try again later."
            logger.error(f"Exception creating Stripe payment for user {user_id}: {e}", exc_info=True)

    # After reminder creation (success or failure)
    # This block will now primarily handle alternative messages if current_operation_status
    # IS correctly propagated and is something other than "success" with the "Done! 🎉" message,
    # or if it is "success" and we want the MSG_REMINDER_SET format.
    # Given the current workaround, if "Done! 🎉" was used, current_operation_status was locally set to "success"
    # for cleanup purposes.

    if current_operation_status == "success":
        # If the "Done! 🎉" message was already set as response_text, we don't want to overwrite it here
        # with MSG_REMINDER_SET unless that's the desired final message.
        # The user wants "Done! 🎉...", so we should ensure it's not overwritten.
        if "Done! 🎉" not in response_text: # Only format with MSG_REMINDER_SET if not already the "Done" message
            reminder_details = state.get("reminder_details", {})
            task = reminder_details.get("task", "your task")
            utc_dt_str = reminder_details.get("datetime_utc_iso")
            if utc_dt_str:
                utc_dt = datetime.datetime.fromisoformat(utc_dt_str.replace("Z", "+00:00"))
                formatted_datetime = format_datetime_for_display(utc_dt)
                response_text = MSG_REMINDER_SET.format(
                    task=task, 
                    date=formatted_datetime, 
                    time=formatted_datetime
                )
            else:
                response_text = f"Your reminder for '{task}' has been set successfully, but there was an error displaying the date and time."
            logger.info(f"handle_intent_node: Formatted MSG_REMINDER_SET for success. Task: {task}")
        
        # Cleanup logic, always run for success
        logger.info(f"handle_intent_node: Success status processed. Task: {state.get('reminder_details', {}).get('task')}")
        updated_state_dict["current_operation_status"] = None 
        updated_state_dict["reminder_details"] = None 

    elif current_operation_status == "limit_reached_free":
        response_text = settings.MSG_REMINDER_LIMIT_REACHED_FREE.format(limit=settings.MAX_REMINDERS_FREE_TIER)
        limit_exceeded_keyboard = {
            "type": "InlineKeyboardMarkup",
            "inline_keyboard": [
                [{"text": "Unlimited Reminders 👑", "callback_data": "show_subscription_options"}]
            ]
        }
        response_keyboard_markup = limit_exceeded_keyboard
        logger.info(f"handle_intent_node: Free tier limit reached for user {user_id}.")
        updated_state_dict["current_operation_status"] = None

    elif current_operation_status == "limit_reached_premium":
        response_text = settings.MSG_REMINDER_LIMIT_REACHED_PREMIUM.format(limit=settings.MAX_REMINDERS_PREMIUM_TIER)
        logger.info(f"handle_intent_node: Premium tier limit reached for user {user_id}.")
        updated_state_dict["current_operation_status"] = None

    elif current_operation_status == "error_db": 
        response_text = "Sorry, a database error occurred while saving your reminder. Please try again."
        logger.error(f"handle_intent_node: DB error during reminder creation for user {user_id}.")
        updated_state_dict["current_operation_status"] = None
    
    elif current_operation_status == "error_missing_data": 
        response_text = "Insufficient information for creating a reminder (such as text or time) was received. Please try again."
        logger.warning(f"handle_intent_node: Missing data for reminder creation for user {user_id}.")
        updated_state_dict["current_operation_status"] = None
    
    elif current_operation_status and "error" in current_operation_status: # Catch other errors from create_reminder_node
        # This handles cases like "error_invalid_datetime_format_in_context", "error_user_not_found", etc.
        # if they set a response_text in create_reminder_node and it made it to the state.
        # If not, it will be the default "I didn't understand..." or the specific error text from create_reminder if used.
        if response_text_from_state and response_text == default_response_text: # If create_node set specific error text
            response_text = response_text_from_state
        logger.error(f"handle_intent_node: Handling generic error status '{current_operation_status}' for user {user_id}. Response: '{response_text}'")
        updated_state_dict["current_operation_status"] = None


    # --- Final preparations before returning from handle_intent_node ---
    updated_state_dict["response_text"] = response_text
    if response_keyboard_markup is not None: 
        updated_state_dict["response_keyboard_markup"] = response_keyboard_markup
    else: 
        updated_state_dict["response_keyboard_markup"] = None

    logger.debug(f"handle_intent_node for user {user_id} returning with response_text: '{response_text[:100]}...', keyboard: {bool(updated_state_dict.get('response_keyboard_markup'))}")
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
    Uses resolve_english_date_phrase_to_range for date phrases.
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
            "filter_processing_status_message": "Filters cleared." # Provide feedback
        }

    date_phrase = extracted_params.get("date_phrase")
    keywords = extracted_params.get("keywords") 

    if date_phrase:
        logger.info(f"User {user_id}: Processing date_phrase for filter: '{date_phrase}'")
        updated_reminder_filters["raw_date_phrase"] = date_phrase
        try:
            start_utc, end_utc = resolve_english_date_phrase_to_range(date_phrase)
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