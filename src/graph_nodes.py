import logging
from typing import Dict, Any, Optional
import json
import google.generativeai as genai
import datetime
import pytz
import jdatetime
from sqlalchemy import func, or_

from src.graph_state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END
from langchain_core.messages import AIMessage # Updated import path
from config.config import settings, MSG_WELCOME # Import settings for API key, model name, AND TIER LIMITS
from src.datetime_utils import parse_persian_datetime_to_utc, resolve_persian_date_phrase_to_range # Import the new parser
from src.database import Reminder, User, get_db # Updated import
from sqlalchemy.orm import Session # Still needed for type hint
# from src.database_session import get_db # Placeholder for session management

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
        user_db_obj = db.query(User).filter(User.user_id == user_id).first()
        
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
            Reminder.user_db_id == user_db_obj.id, 
            Reminder.is_active == True
        ).scalar() or 0

        max_reminders = settings.MAX_REMINDERS_PREMIUM_TIER if user_db_obj.is_premium else settings.MAX_REMINDERS_FREE_TIER

        user_profile_data = {
            "user_db_id": user_db_obj.id,
            "username": user_db_obj.username,
            "first_name": user_db_obj.first_name,
            "last_name": user_db_obj.last_name,
            "is_premium": user_db_obj.is_premium,
            "premium_until": user_db_obj.premium_until.isoformat() if user_db_obj.premium_until else None,
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
    """Node to determine user intent and extract parameters using Gemini,
    handling pending clarifications and confirmations."""
    logger.info(f"Graph: Entered determine_intent_node for user {state.get('user_id')}")
    input_text = state.get("input_text", "").strip()
    transcribed_text = state.get("transcribed_text", "").strip()
    message_type = state.get("message_type")
    user_id = state.get("user_id")

    effective_input = input_text if input_text else transcribed_text
    
    # Initialize reminder_creation_context if not present
    reminder_creation_context = state.get("reminder_creation_context") if state.get("reminder_creation_context") is not None else {}
    pending_clarification_type = reminder_creation_context.get("pending_clarification_type")
    pending_confirmation_type = state.get("pending_confirmation")

    # Initialize extracted_parameters safely
    current_extracted_parameters = state.get("extracted_parameters") if state.get("extracted_parameters") is not None else {}
    
    nlu_raw_output_for_state: Optional[Dict[str, Any]] = None

    # --- Start: Handle Specific Callbacks for Pending Clarifications ---
    if pending_clarification_type and message_type == "callback_query":
        logger.info(f"Handling callback for pending_clarification_type: '{pending_clarification_type}', callback_data: '{effective_input}'")
        clarification_handled_directly = False
        parsed_parameters_for_clarification = {}

        if pending_clarification_type == "am_pm":
            if effective_input == "clarify_am_pm:am":
                parsed_parameters_for_clarification["am_pm_choice"] = "am"
                clarification_handled_directly = True
            elif effective_input == "clarify_am_pm:pm":
                parsed_parameters_for_clarification["am_pm_choice"] = "pm"
                clarification_handled_directly = True
        
        # Add other direct callback clarifications here if needed in the future

        if clarification_handled_directly:
            logger.info(f"Directly handled clarification '{pending_clarification_type}' with params: {parsed_parameters_for_clarification}")
            reminder_creation_context["collected_am_pm_choice"] = parsed_parameters_for_clarification["am_pm_choice"] # Example for am_pm
            # reminder_creation_context.update(parsed_parameters_for_clarification) # Generic way to merge
            
            reminder_creation_context["pending_clarification_type"] = None
            reminder_creation_context["status"] = None # Reset status, will be re-evaluated
            
            # The intent should become intent_create_reminder to re-process with the new info
            # NLU output is simulated as if Gemini provided this clarification
            simulated_nlu_output = {"intent": "intent_provide_clarification", "parameters": parsed_parameters_for_clarification}

            # Merge parameters from context into current_extracted_parameters for process_datetime_node
            if reminder_creation_context.get("collected_task"):
                current_extracted_parameters["task"] = reminder_creation_context["collected_task"]
            if reminder_creation_context.get("collected_date_str"):
                current_extracted_parameters["date"] = reminder_creation_context["collected_date_str"]
            if reminder_creation_context.get("collected_time_str"):
                current_extracted_parameters["time"] = reminder_creation_context["collected_time_str"]
            if reminder_creation_context.get("collected_am_pm_choice"):
                 current_extracted_parameters["am_pm_choice"] = reminder_creation_context.get("collected_am_pm_choice")

            return {
                "current_intent": "intent_create_reminder", # Re-evaluate with new info
                "extracted_parameters": current_extracted_parameters, # Pass merged params
                "nlu_direct_output": {"direct_clarification_resolution": simulated_nlu_output},
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": reminder_creation_context, # Updated context
                "pending_confirmation": pending_confirmation_type # Pass through
            }
        # If not handled directly, fall through to NLU or other logic for the callback
        logger.info(f"Callback for '{pending_clarification_type}' not handled directly, proceeding to other logic.")
    # --- End: Handle Specific Callbacks for Pending Clarifications ---

    # --- Start: Handle Direct Action Callbacks (e.g., pagination) ---
    if message_type == "callback_query" and not pending_clarification_type and not pending_confirmation_type:
        # This section handles callbacks that are direct actions, not part of a clarification or confirmation sequence.
        parsed_intent = "unknown_intent"
        parsed_parameters = {}
        action_callback_handled = False

        if effective_input.startswith("view_reminders:page:"):
            try:
                page_num_str = effective_input.split(":")[-1]
                page_num = int(page_num_str)
                parsed_intent = "intent_view_reminders"
                parsed_parameters = {"page": page_num} 
                action_callback_handled = True
                logger.info(f"Direct action callback: view_reminders pagination to page {page_num}")
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not parse page number from view_reminders callback: {effective_input}. Error: {e}")
                # Let it fall through, might be handled by general NLU or other logic if it's a malformed callback
        elif effective_input.startswith("clear_filters_view_reminders:page:"):
            try:
                page_num_str = effective_input.split(":")[-1]
                page_num = int(page_num_str)
                parsed_intent = "intent_view_reminders"
                parsed_parameters = {"page": page_num, "clear_filters_action": True}
                action_callback_handled = True
                logger.info(f"Direct action callback: clear_filters_view_reminders and show page {page_num}")
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not parse page number from clear_filters_view_reminders callback: {effective_input}. Error: {e}")

        # Add other direct action callbacks here, e.g., snooze:duration:id

        if action_callback_handled:
            return {
                "current_intent": parsed_intent,
                "extracted_parameters": parsed_parameters,
                "nlu_direct_output": {"direct_action_callback": effective_input, "parsed_as": parsed_intent, "params": parsed_parameters},
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": reminder_creation_context, # Pass through
                "pending_confirmation": None # No pending confirmation for these direct actions
            }
    # --- End: Handle Direct Action Callbacks ---

    # --- Start: Handle Pre-set Intents or Direct Command Matches ---
    # This section handles intents set by bot.py or simple command matches
    # If an intent is pre-set (e.g., by a command handler in bot.py), use it directly.
    pre_set_intent = state.get("current_intent")
    if pre_set_intent and not pending_clarification_type and not pending_confirmation_type:
        # Only use pre-set intent if not in a clarification/confirmation loop,
        # as those loops need to re-evaluate intent based on specific user replies.
        logger.info(f"Intent '{pre_set_intent}' was pre-set for input '{effective_input}'. Using it directly.")
        return {
            "current_intent": pre_set_intent,
            "extracted_parameters": current_extracted_parameters,
            "nlu_direct_output": {"pre_set_intent": pre_set_intent, "pre_set_parameters": current_extracted_parameters},
            "current_node_name": "determine_intent_node",
            "reminder_creation_context": reminder_creation_context, # Pass through
            "pending_confirmation": pending_confirmation_type # Pass through
        }

    # Handle direct commands like /start, /help etc.
    if message_type == "command" or message_type == "command_webhook_simulation":
        if effective_input == "/start":
            logger.info("Direct command match: /start. Setting intent to intent_start_app.")
            return {"current_intent": "intent_start_app", "extracted_parameters": {}, "nlu_direct_output": {"direct_match": "/start"}, "current_node_name": "determine_intent_node", "reminder_creation_context": reminder_creation_context, "pending_confirmation": None}
        if effective_input == "/privacy":
            logger.info("Direct command match: /privacy. Setting intent to intent_show_privacy_policy.")
            return {"current_intent": "intent_show_privacy_policy", "extracted_parameters": {}, "nlu_direct_output": {"direct_match": "/privacy"}, "current_node_name": "determine_intent_node", "reminder_creation_context": reminder_creation_context, "pending_confirmation": None}
        # Add other direct commands here: /help, /pay, /reminders, /cancel
        # Example for /cancel (if it always leads to intent_cancel_operation)
        if effective_input == "/cancel":
            logger.info("Direct command match: /cancel. Setting intent to intent_cancel_operation.")
            return {"current_intent": "intent_cancel_operation", "extracted_parameters": {}, "nlu_direct_output": {"direct_match": "/cancel"}, "current_node_name": "determine_intent_node", "reminder_creation_context": {}, "pending_confirmation": None} # Clear context on cancel
    # --- End: Handle Pre-set Intents or Direct Command Matches ---

    # --- Start: Handle Pending Confirmations (from callbacks) ---
    if pending_confirmation_type and message_type == "callback_query":
        logger.info(f"Handling pending confirmation '{pending_confirmation_type}' with callback data: '{effective_input}'")
        parsed_intent = "unknown_intent"
        parsed_parameters = {}

        if pending_confirmation_type == "create_reminder":
            if effective_input == "confirm_create_reminder:yes":
                parsed_intent = "intent_create_reminder_confirmed"
            elif effective_input == "confirm_create_reminder:no":
                parsed_intent = "intent_create_reminder_cancelled"
            
        # Add other pending_confirmation_types here, e.g., "delete_reminder"
        # if pending_confirmation_type == "delete_reminder":
        #     if effective_input.startswith("confirm_delete_reminder:yes"):
        #         parsed_intent = "intent_delete_reminder_confirmed"
        #         # Potentially extract ID if it's part of the callback data again
        #         # parsed_parameters = {"reminder_id": effective_input.split(':')[-1]}
        #     elif effective_input == "confirm_delete_reminder:no":
        #         parsed_intent = "intent_delete_reminder_cancelled"
        elif pending_confirmation_type == "view_reminders_pagination": # Check if this is a pagination callback
            if effective_input.startswith("view_reminders:page:"):
                try:
                    page_num_str = effective_input.split(":")[-1]
                    page_num = int(page_num_str)
                    # We set intent to view_reminders, and store page in extracted_parameters
                    # The handle_intent_node will then use this page number.
                    parsed_intent = "intent_view_reminders"
                    parsed_parameters = {"page": page_num} # Store page number
                    logger.info(f"Callback for view_reminders pagination: page {page_num}")
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse page number from callback data: {effective_input}. Error: {e}")
                    # Fall through to general NLU or let it be handled as unknown if it doesn't match other patterns

        if parsed_intent != "unknown_intent":
            logger.info(f"Callback for pending confirmation resolved to intent: {parsed_intent}")
            return {
                "current_intent": parsed_intent,
                "extracted_parameters": parsed_parameters, # Parameters might be empty or extracted if needed
                "nlu_direct_output": {"confirmation_resolution": parsed_intent, "callback_data": effective_input},
                "current_node_name": "determine_intent_node",
                "reminder_creation_context": reminder_creation_context, # Pass context
                "pending_confirmation": None # Clear pending confirmation
            }
        else:
            logger.warning(f"Callback '{effective_input}' did not match expected format for pending confirmation '{pending_confirmation_type}'. Proceeding to general NLU.")
            # Fall through to general NLU if callback doesn't match expected patterns for this confirmation
    # --- End: Handle Pending Confirmations ---


    if not effective_input:
        logger.warning(f"No effective input text for NLU for user {user_id}. Returning unknown_intent.")
        return {"current_intent": "unknown_intent", "extracted_parameters": {}, "nlu_direct_output": None, "current_node_name": "determine_intent_node", "reminder_creation_context": reminder_creation_context, "pending_confirmation": pending_confirmation_type}

    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Skipping NLU.")
        return {"current_intent": "unknown_intent", "extracted_parameters": {"error_in_nlu": "API key missing"}, "nlu_direct_output": {"error": "GEMINI_API_KEY not set"}, "current_node_name": "determine_intent_node", "reminder_creation_context": reminder_creation_context, "pending_confirmation": pending_confirmation_type}

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
        
        prompt_parts = [
            "You are an expert intent detection and parameter extraction system for a Telegram reminder bot in Persian."
        ]

        # --- Start: Tailor NLU Prompt for Pending Clarifications ---
        if pending_clarification_type:
            logger.info(f"Handling pending clarification of type: {pending_clarification_type} for user {user_id}")
            prompt_parts.append("The user is currently in the process of creating a reminder and needs to provide a missing piece of information.")
            
            collected_task = reminder_creation_context.get("collected_task")
            collected_date = reminder_creation_context.get("collected_date_str")
            collected_time = reminder_creation_context.get("collected_time_str")

            if pending_clarification_type == "task":
                prompt_parts.append("The bot previously asked for the reminder's task description.")
                prompt_parts.append("The user's input below is expected to be the task description.")
                prompt_parts.append("Extract the 'task' (string). The intent should be 'intent_provide_clarification'.")
                prompt_parts.append(f"User input: \\\"{effective_input}\\\"")
                prompt_parts.append("Example Output: { \"intent\": \"intent_provide_clarification\", \"parameters\": { \"task\": \"خرید شیر\" } }")

            elif pending_clarification_type == "datetime":
                if collected_task:
                    prompt_parts.append(f"The bot previously asked for the date and time for the reminder task: '{collected_task}'.")
                else: # Should ideally not happen if task is always asked first
                    prompt_parts.append("The bot previously asked for the date and time of a reminder.")
                prompt_parts.append("The user's input below is expected to be the date and time.")
                prompt_parts.append("Extract 'date' (string) and 'time' (string). The intent should be 'intent_provide_clarification'.")
                prompt_parts.append(f"User input: \\\"{effective_input}\\\"")
                prompt_parts.append("Example Output: { \"intent\": \"intent_provide_clarification\", \"parameters\": { \"date\": \"فردا\", \"time\": \"۱۰ صبح\" } }")
            
            elif pending_clarification_type == "am_pm":
                ambiguous_hour = reminder_creation_context.get("ambiguous_time_details", {}).get("hour", "a specific time")
                prompt_parts.append(f"The bot previously asked whether '{ambiguous_hour}' refers to AM or PM (صبح یا بعد از ظهر).")
                prompt_parts.append("The user's input below is expected to be 'صبح' (AM), 'بعد از ظهر' (PM), or similar affirmation indicating their choice.")
                prompt_parts.append("Extract 'am_pm_choice' ('am' or 'pm'). The intent should be 'intent_provide_clarification'.")
                prompt_parts.append(f"User input: \\\"{effective_input}\\\"")
                prompt_parts.append("Example Output for 'صبح': { \"intent\": \"intent_provide_clarification\", \"parameters\": { \"am_pm_choice\": \"am\" } }")
                prompt_parts.append("Example Output for 'بعد از ظهر': { \"intent\": \"intent_provide_clarification\", \"parameters\": { \"am_pm_choice\": \"pm\" } }")
            
            else: # Fallback to general prompt if clarification type is unknown
                logger.warning(f"Unknown pending_clarification_type: {pending_clarification_type}. Using general NLU prompt.")
                pending_clarification_type = None # Reset to avoid issues
                # This will make it fall through to the general NLU prompt logic below
        # --- End: Tailor NLU Prompt ---

        if not pending_clarification_type: # General NLU prompt
            prompt_parts.extend([
                "Analyze the following user input in Persian and determine the user's intent and extract relevant parameters.",
                f"User input: \\\"{effective_input}\\\"",
                "Possible intents are:",
                "- intent_start_app: User sends /start command or equivalent greeting.",
                "- intent_create_reminder: User wants to create a new reminder (this is the primary intent if task/date/time are mentioned).",
                "- intent_view_reminders: User wants to see their existing reminders. Can include page number parameter from callback e.g. { \\\"page\\\": 1 }. Can also include filter parameters like { \\\"date_phrase\\\": \\\"فردا\\\", \\\"keywords\\\": [\\\"جلسه\\\"] }.",
                "- intent_edit_reminder: User wants to modify an existing reminder.",
                "- intent_delete_reminder: User wants to delete a reminder.",
                "- intent_help: User is asking for help or instructions (e.g. /help).",
                "- intent_payment_initiate: User wants to start the payment process (e.g. /pay).",
                "- intent_payment_callback_process: System needs to process a payment callback.",
                "- intent_cancel_operation: User wants to cancel the current multi-step operation (e.g. /cancel).",
                "- intent_show_privacy_policy: User wants to see the privacy policy (e.g. /privacy).",
                "- intent_greeting, intent_farewell, intent_affirmation, intent_negation.",
                "- intent_clarification_needed: Input is too vague.",
                "- unknown_intent: If none of the above.",
                # New intents for confirmation flow
                "- intent_create_reminder_confirmed: User confirms to proceed with reminder creation (usually from a 'yes' callback).",
                "- intent_create_reminder_cancelled: User cancels reminder creation (usually from a 'no' callback).",
                # "- intent_delete_reminder_confirmed: User confirms deletion.", (Example for future)
                # "- intent_delete_reminder_cancelled: User cancels deletion.", (Example for future)
                "If the input is a command like '/help', classify it as 'intent_help'.",
                "If the input looks like callback_data (e.g., 'action:value1', 'confirm_create_reminder:yes'), classify its intent accordingly.",
                "  Example callback_data: 'confirm_create_reminder:yes' -> intent_create_reminder_confirmed",
                "  Example callback_data: 'confirm_create_reminder:no' -> intent_create_reminder_cancelled",
                "  Example callback_data: 'delete_reminder:ID:PAGE' -> intent_delete_reminder, parameters: {reminder_id: ID, page: PAGE}",
                "  Example callback_data: 'view_reminders:page:1' -> intent_view_reminders, parameters: {page: 1}",

                "Parameters for 'intent_create_reminder', 'intent_edit_reminder':",
                "- task (string): The description of the reminder.",
                "- date (string): The date. Keep it as mentioned.",
                "- time (string): The time. Keep it as mentioned.",
                "- relative_occurrence (string, optional): e.g., 'هر روز'.",
                # (Other parameter extraction rules as before)
                "Output ONLY a JSON object with two keys: \\\"intent\\\" and \\\"parameters\\\".",
                "Example for intent_create_reminder: { \\\"intent\\\": \\\"intent_create_reminder\\\", \\\"parameters\\\": { \\\"task\\\": \\\"جلسه\\\", \\\"date\\\": \\\"فردا\\\", \\\"time\\\": \\\"۱۰ صبح\\\" } }",

                "Parameters for 'intent_view_reminders' (if filtering):",
                "- date_phrase (string, optional): A phrase describing a date or date range, e.g., 'امروز', 'این هفته', 'ماه آینده'.",
                "- keywords (list of strings, optional): Keywords to search in the task description.",

                "Output ONLY a JSON object with two keys: \\\"intent\\\" and \\\"parameters\\\".",
                "Example for intent_view_reminders: { \\\"intent\\\": \\\"intent_view_reminders\\\", \\\"parameters\\\": { \\\"date_phrase\\\": \\\"فردا\\\", \\\"keywords\\\": [\\\"جلسه\\\"] } }"
            ])

        prompt_parts.append("Output ONLY a JSON object with two keys: \\\"intent\\\" and \\\"parameters\\\". 'parameters' should be an object. If no parameters, 'parameters' should be an empty object.")
        prompt = "\\n".join(prompt_parts)
        
        logger.debug(f"Sending prompt to Gemini for user {user_id}:\\n{prompt[:1000]}...")
        response = await model.generate_content_async(prompt)
        
        parsed_intent = "unknown_intent"
        parsed_parameters = {}

        if response.text:
            logger.debug(f"Gemini response raw text: {response.text}")
            cleaned_response_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
            parsed_response_json = json.loads(cleaned_response_text)
            parsed_intent = parsed_response_json.get("intent", "unknown_intent")
            parsed_parameters = parsed_response_json.get("parameters", {})
            nlu_raw_output_for_state = parsed_response_json
            logger.info(f"Gemini NLU result: Intent='{parsed_intent}', Parameters='{parsed_parameters}'")

            # --- Start: Merge Clarified Parameters and Clear Pending State ---
            if pending_clarification_type and parsed_intent == "intent_provide_clarification":
                logger.info(f"Merging clarified parameters for type: {pending_clarification_type}")
                if "task" in parsed_parameters and pending_clarification_type == "task":
                    reminder_creation_context["collected_task"] = parsed_parameters["task"]
                if "date" in parsed_parameters and "time" in parsed_parameters and pending_clarification_type == "datetime":
                    reminder_creation_context["collected_date_str"] = parsed_parameters["date"]
                    reminder_creation_context["collected_time_str"] = parsed_parameters["time"]
                if "am_pm_choice" in parsed_parameters and pending_clarification_type == "am_pm":
                    # This choice needs to be applied in process_datetime_node or a new AM/PM processing node
                    reminder_creation_context["collected_am_pm_choice"] = parsed_parameters["am_pm_choice"]
                
                # Important: After processing clarification, the intent should likely revert to intent_create_reminder
                # so the main flow can resume validation and processing with the new info.
                # The router will then send it to process_datetime_node and then validate_and_clarify_reminder_node.
                
                # Clear the pending clarification type
                reminder_creation_context["pending_clarification_type"] = None
                reminder_creation_context["status"] = None # Reset status
                logger.info(f"Cleared pending_clarification_type. Updated reminder_creation_context: {reminder_creation_context}")

            elif pending_clarification_type and parsed_intent != "intent_provide_clarification":
                 logger.warning(f"User input was expected to be a clarification for '{pending_clarification_type}', but NLU returned intent '{parsed_intent}'. Retaining pending clarification.")
            # --- End: Merge Clarified Parameters ---

        else:
            logger.warning(f"Gemini returned no text in response for input: {effective_input}")
            nlu_raw_output_for_state = {"error": "Gemini returned no text", "response_object": str(response) if 'response' in locals() else 'N/A'}

        # Update extracted_parameters with any new parameters if not a clarification merge
        # If it was a clarification, parsed_parameters contain just the clarified bit.
        # The full set of parameters for create_reminder will be in reminder_creation_context.
        # For now, we return parsed_parameters as Gemini extracted. Subsequent nodes must be aware.
        
        # If the original intent was 'intent_create_reminder' and it's still the case (not a clarification that changes it)
        # ensure that all collected parameters are in 'extracted_parameters' for the next nodes.
        if parsed_intent == "intent_create_reminder":
            # Merge parameters from context into parsed_parameters for process_datetime_node
            if reminder_creation_context.get("collected_task"):
                parsed_parameters["task"] = reminder_creation_context["collected_task"]
            if reminder_creation_context.get("collected_date_str"):
                parsed_parameters["date"] = reminder_creation_context["collected_date_str"]
            if reminder_creation_context.get("collected_time_str"):
                parsed_parameters["time"] = reminder_creation_context["collected_time_str"]
            # Also add am/pm choice if available for process_datetime_node
            if reminder_creation_context.get("collected_am_pm_choice"):
                 parsed_parameters["am_pm_choice"] = reminder_creation_context.get("collected_am_pm_choice")


        return {
            "current_intent": parsed_intent,
            "extracted_parameters": parsed_parameters,
            "nlu_direct_output": nlu_raw_output_for_state,
            "current_node_name": "determine_intent_node",
            "reminder_creation_context": reminder_creation_context, # Ensure updated context is passed
            "pending_confirmation": state.get("pending_confirmation") # Pass through if not cleared by confirmation logic
        }

    except json.JSONDecodeError as e:
        raw_text_for_error = response.text if 'response' in locals() and hasattr(response, 'text') else 'N/A'
        logger.error(f"Failed to parse JSON response from Gemini: {e}. Response text: {raw_text_for_error}")
        nlu_raw_output_for_state = {"error": "JSONDecodeError", "raw_text": raw_text_for_error, "exception": str(e)}
    except Exception as e:
        logger.error(f"Error calling Gemini API or processing response: {e}", exc_info=True)
        nlu_raw_output_for_state = {"error": "Gemini API or processing error", "exception": str(e)}

    return {
        "current_intent": "unknown_intent",
        "extracted_parameters": {"error_in_nlu": True},
        "nlu_direct_output": nlu_raw_output_for_state,
        "current_node_name": "determine_intent_node",
        "reminder_creation_context": reminder_creation_context, # Pass context even on error
        "pending_confirmation": state.get("pending_confirmation") # Pass through
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
        user_obj = db.query(User).filter(User.user_id == user_id).first()

        if not user_obj:
            logger.info(f"User {user_id} not found. Creating new user.")
            if not user_telegram_details: # These details are important for new user creation
                logger.warning(f"execute_start_command_node: user_telegram_details missing for new user {user_id}. User record will be incomplete.")
                # Fallback to empty strings if details are missing, though ideally they should be passed.
                user_telegram_details = {"username": None, "first_name": "User", "last_name": None, "language_code": "en"}
            
            user_obj = User(
                user_id=user_id,
                chat_id=chat_id,
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
                "is_premium": user_obj.is_premium,
                "premium_until": None,
                "language_code": user_obj.language_code,
                "reminder_limit": settings.MAX_REMINDERS_FREE_TIER,
                "current_reminder_count": 0
            }
        else:
            logger.info(f"User {user_id} found. Updating details if necessary.")
            # Update chat_id and other details if they might change
            needs_commit = False
            if user_obj.chat_id != chat_id:
                user_obj.chat_id = chat_id
                needs_commit = True
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
            "type": "ReplyKeyboardMarkup",
            "keyboard": [
                [{"text": "یادآورهای من"}, {"text": "راهنما"}],
                [{"text": "پرداخت حق اشتراک"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False # Usually welcome keyboard is not one_time
        }

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
    
    # Fields for parsing
    date_str = reminder_ctx.get("collected_date_str") or extracted_params.get("date")
    time_str = reminder_ctx.get("collected_time_str") or extracted_params.get("time")
    # AM/PM choice can also come from context or direct params (if NLU provides it initially)
    am_pm_choice = reminder_ctx.get("collected_am_pm_choice") or extracted_params.get("am_pm_choice")


    # Only attempt parsing if intent is reminder-related and parameters are present
    # For intent_create_reminder, this node is always called if intent is matched.
    # No longer checking reminder_intents here as routing logic handles it.
    if current_intent == "intent_create_reminder": # Or if it's an edit flow later
        if date_str or time_str:
            logger.info(f"Attempting to parse date='{date_str}', time='{time_str}', am_pm='{am_pm_choice}' for intent '{current_intent}'")
            try:
                # Pass am_pm_choice to the parser if available
                parsed_dt_utc = parse_persian_datetime_to_utc(date_str, time_str, am_pm_choice=am_pm_choice)
                if parsed_dt_utc:
                    logger.info(f"Successfully parsed datetime to UTC: {parsed_dt_utc}")
                    # Store in context for subsequent nodes
                    reminder_ctx["collected_parsed_datetime_utc"] = parsed_dt_utc
                    # Clear am_pm_choice from context once used for parsing
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
    user_profile = state.get("user_profile", {})

    collected_task = reminder_ctx.get("collected_task")
    collected_parsed_dt_utc = reminder_ctx.get("collected_parsed_datetime_utc")
    # collected_date_str = reminder_ctx.get("collected_date_str") # Raw strings
    # collected_time_str = reminder_ctx.get("collected_time_str") # Raw strings
    
    current_reminder_count = user_profile.get("current_reminder_count", 0)
    reminder_limit = user_profile.get("reminder_limit", settings.MAX_REMINDERS_FREE_TIER)
    is_premium = user_profile.get("is_premium", False)

    new_reminder_creation_status: Optional[str] = None
    pending_clarification_type: Optional[str] = None
    clarification_question_text: Optional[str] = None
    clarification_keyboard_markup: Optional[Dict[str, Any]] = None

    # 1. Check Tier Limits first
    if current_reminder_count >= reminder_limit:
        logger.warning(f"User {user_id} at reminder limit ({current_reminder_count}/{reminder_limit}), Premium: {is_premium}. Cannot create new reminder.")
        new_reminder_creation_status = "error_limit_exceeded"
        # This status will be handled by handle_intent_node to inform the user.
        # No further validation or clarification needed if limit is reached.
        reminder_ctx["status"] = new_reminder_creation_status
        return {
            "reminder_creation_context": reminder_ctx,
            "reminder_creation_status": new_reminder_creation_status,
            "current_node_name": "validate_and_clarify_reminder_node"
        }

    # 2. Validate Task
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

    return {
        "reminder_creation_context": reminder_ctx,
        "reminder_creation_status": new_reminder_creation_status, # This will be used by router
        "current_node_name": "validate_and_clarify_reminder_node"
    }

async def confirm_reminder_details_node(state: AgentState) -> Dict[str, Any]:
    """
    Prepares a confirmation message and buttons for the user to confirm reminder creation.
    Sets the pending_confirmation state.
    """
    user_id = state.get("user_id")
    logger.info(f"Graph: Entered confirm_reminder_details_node for user {user_id}")

    reminder_ctx = state.get("reminder_creation_context", {})
    task = reminder_ctx.get("collected_task")
    parsed_utc_datetime = reminder_ctx.get("collected_parsed_datetime_utc")

    if not task or not parsed_utc_datetime:
        logger.error(f"Cannot confirm reminder for user {user_id}: task or parsed_datetime_utc missing from context. Task: {task}, DT: {parsed_utc_datetime}")
        # This should not happen if routing is correct (i.e., only called when "ready_for_confirmation")
        return {
            "reminder_creation_context": reminder_ctx,
            "reminder_creation_status": "error_missing_details_for_confirmation",
            "pending_confirmation": None, # Ensure it's not set
            "current_node_name": "confirm_reminder_details_node"
        }

    try:
        tehran_tz = pytz.timezone('Asia/Tehran')
        parsed_tehran_datetime = parsed_utc_datetime.astimezone(tehran_tz)
        jalali_dt = jdatetime.datetime.fromgregorian(datetime=parsed_tehran_datetime)
        display_datetime_str = jalali_dt.strftime("%Y/%m/%d ساعت %H:%M")
        confirmation_question = f"قصد ایجاد یادآور برای «{task}» در تاریخ «{display_datetime_str}» (به وقت تهران) را دارید. آیا تایید می‌کنید؟"
    except Exception as e:
        logger.error(f"Error formatting datetime for confirmation message (user {user_id}): {e}", exc_info=True)
        confirmation_question = f"قصد ایجاد یادآور برای «{task}» را دارید. آیا تایید می‌کنید؟ (خطا در نمایش زمان)"

    confirmation_keyboard = {
        "type": "InlineKeyboardMarkup",
        "inline_keyboard": [
            [
                {"text": "✅ بله، ایجاد کن", "callback_data": "confirm_create_reminder:yes"},
                {"text": "❌ خیر، لغو کن", "callback_data": "confirm_create_reminder:no"}
            ]
        ]
    }

    reminder_ctx["confirmation_question_text"] = confirmation_question
    reminder_ctx["confirmation_keyboard_markup"] = confirmation_keyboard
    
    logger.info(f"User {user_id}: Prepared confirmation for task '{task}' at '{display_datetime_str}'. Setting pending_confirmation.")

    return {
        "reminder_creation_context": reminder_ctx,
        "pending_confirmation": "create_reminder", # Signal that we are waiting for this specific confirmation
        "reminder_creation_status": "awaiting_confirmation", # New status
        "current_node_name": "confirm_reminder_details_node"
    }

async def create_reminder_node(state: AgentState) -> Dict[str, Any]:
    """
    Creates a reminder in the database.
    Assumes parameters are now in reminder_creation_context and validated,
    and user has confirmed (intent is intent_create_reminder_confirmed).
    Updates reminder_creation_status.
    """
    logger.info(f"Graph: Entered create_reminder_node for user {state.get('user_id')}")
    telegram_user_id_from_state = state.get("user_id")
    chat_id = state.get("chat_id")
    # Get validated details from reminder_creation_context
    reminder_ctx = state.get("reminder_creation_context", {})
    validated_task = reminder_ctx.get("collected_task")
    parsed_utc_datetime = reminder_ctx.get("collected_parsed_datetime_utc")
    # current_intent should be 'intent_create_reminder_confirmed' or similar to reach here after confirmation
    current_intent = state.get("current_intent") 
    
    status: Optional[str] = "db_error" # Default to error
    user_profile = state.get("user_profile")

    if not user_profile or not user_profile.get("user_db_id"):
        logger.error(f"User profile or user_db_id missing in create_reminder_node for user {telegram_user_id_from_state}")
        # This case should ideally be handled by load_user_profile_node earlier
        # or the user creation part of execute_start_command_node.
        # If a user gets here without a profile, it's an issue.
        return {
            "reminder_creation_status": "error_user_not_found",
            "current_node_name": "create_reminder_node",
            "reminder_creation_context": reminder_ctx # Return context
        }

    user_db_id = user_profile["user_db_id"]
    is_premium = user_profile.get("is_premium", False)
    max_reminders_for_tier = user_profile.get("reminder_limit", settings.MAX_REMINDERS_FREE_TIER)
    current_reminder_count = user_profile.get("current_reminder_count", 0)


    # Ensure intent is one that confirms creation, e.g., "intent_create_reminder_confirmed"
    # or for simplicity, we can check if task and datetime are present after validation.
    # The routing logic should ensure we only get here if confirmed.
    if current_intent == "intent_create_reminder_confirmed" and validated_task and parsed_utc_datetime and telegram_user_id_from_state and chat_id:
        logger.info(f"Attempting to create reminder for telegram_user_id={telegram_user_id_from_state}, task='{validated_task}'")
        
        # Tier limit check (using already loaded user_profile data)
        if current_reminder_count >= max_reminders_for_tier:
            logger.warning(f"User {telegram_user_id_from_state} (DB ID {user_db_id}) has reached reminder limit. Count: {current_reminder_count}, Limit: {max_reminders_for_tier}, Premium: {is_premium}")
            status = "error_limit_exceeded"
        else:
            db: Session = next(get_db())
            try:
                # User object should exist due to load_user_profile_node or start_command.
                # We use user_db_id from the profile.
                logger.info(f"User {telegram_user_id_from_state} (DB ID {user_db_id}) reminder check passed. Count: {current_reminder_count}, Limit: {max_reminders_for_tier}")
                new_reminder = Reminder(
                    user_db_id=user_db_id, # Use ID from profile
                    telegram_user_id=telegram_user_id_from_state,
                    chat_id=chat_id,
                    task_description=validated_task,
                    due_datetime_utc=parsed_utc_datetime,
                    is_active=True,
                    is_sent=False
                    # recurrence_rule can be added from reminder_ctx if collected
                )
                db.add(new_reminder)
                db.commit()
                logger.info(f"Reminder created successfully for user DB ID {user_db_id}, task: '{validated_task}'")
                status = "success"
                # Update user_profile's current_reminder_count if successful
                if user_profile: # Should exist
                    user_profile["current_reminder_count"] = current_reminder_count + 1

            except Exception as e:
                logger.error(f"Database error during reminder creation for Telegram user {telegram_user_id_from_state}: {e}", exc_info=True)
                if db: db.rollback()
                status = "db_error" # Already default, but explicit
            finally:
                if db: db.close()
            
    elif current_intent == "intent_create_reminder_confirmed": # but params invalid (should not happen if routing is correct)
        logger.warning(f"Create reminder node called for '{current_intent}' but parameters were invalid. Task: '{validated_task}', Datetime: {parsed_utc_datetime}")
        status = reminder_ctx.get("status") or "error_validation_failed_before_creation"
        if not telegram_user_id_from_state: status = "error_missing_user_id"
        if not chat_id: status = "error_missing_chat_id"

    # Clear context after successful creation or if it's a definitive end to this creation attempt (like limit exceeded)
    if status == "success" or status == "error_limit_exceeded":
        final_reminder_ctx = {} # Clear context
    else:
        final_reminder_ctx = reminder_ctx # Preserve context on other errors for potential retry/debug

    return {
        "reminder_creation_status": status,
        "current_node_name": "create_reminder_node",
        "reminder_creation_context": final_reminder_ctx, # Return cleared or preserved context
        "user_profile": user_profile # Return potentially updated profile
    }

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Node to handle the determined intent and craft a response based on graph state."""
    user_id = state.get("user_id")
    logger.info(f"Graph: Entered handle_intent_node for user {user_id}")
    
    intent = state.get("current_intent", "unknown_intent")
    params = state.get("extracted_parameters", {})
    raw_input_text = state.get("input_text", "")
    
    reminder_ctx = state.get("reminder_creation_context", {})
    # Get creation status set by previous nodes (validate_and_clarify, create_reminder, confirm_details)
    current_reminder_status = state.get("reminder_creation_status") 
    
    # Details for messages if available
    collected_task = reminder_ctx.get("collected_task")
    collected_parsed_dt_utc = reminder_ctx.get("collected_parsed_datetime_utc")

    response_text = f"متوجه منظور شما نشدم: '{raw_input_text}'. می‌توانید از دستور /help استفاده کنید."
    response_keyboard_markup = None
    ai_message_content = response_text # Default for AIMessage

    # --- A. Handle states related to reminder creation lifecycle (driven by reminder_creation_status) ---
    if current_reminder_status:
        if current_reminder_status == "success":
            if collected_task and collected_parsed_dt_utc:
                try:
                    tehran_tz = pytz.timezone('Asia/Tehran')
                    parsed_tehran_datetime = collected_parsed_dt_utc.astimezone(tehran_tz)
                    jalali_from_gregorian = jdatetime.datetime.fromgregorian(datetime=parsed_tehran_datetime)
                    display_datetime_str = jalali_from_gregorian.strftime("%Y/%m/%d ساعت %H:%M")
                    response_text = f"یادآور شما برای «{collected_task}» در تاریخ «{display_datetime_str}» (به وقت تهران) با موفقیت ایجاد شد."
                except Exception as e:
                    logger.error(f"Error formatting successful reminder message for user {user_id}: {e}", exc_info=True)
                    response_text = f"یادآور شما برای «{collected_task or 'وظیفه نامشخص'}» با موفقیت ایجاد شد (خطا در نمایش به وقت محلی)."
            else:
                response_text = "یادآور شما با موفقیت ایجاد شد، اما جزئیات برای نمایش موجود نیست."
        
        elif current_reminder_status == "error_limit_exceeded":
            user_profile = state.get("user_profile", {})
            limit = user_profile.get("reminder_limit", settings.MAX_REMINDERS_FREE_TIER)
            is_premium = user_profile.get("is_premium", False)
            if is_premium:
                response_text = f"شما به حداکثر تعداد یادآورهای فعال خود ({limit}) برای کاربران ویژه رسیده‌اید. برای ایجاد یادآور جدید، ابتدا یکی از یادآورهای قبلی خود را حذف کنید."
            else:
                response_text = f"شما به حداکثر تعداد یادآورهای فعال خود ({limit}) برای کاربران رایگان رسیده‌اید. برای ایجاد یادآور جدید، لطفاً اشتراک خود را ارتقا دهید یا یکی از یادآورهای قبلی را حذف کنید."

        elif current_reminder_status == "clarification_needed_task" or current_reminder_status == "clarification_needed_datetime" or current_reminder_status == "clarification_needed_am_pm": 
            # These statuses are set by validate_and_clarify_reminder_node, which also sets the question and keyboard in context.
            response_text = reminder_ctx.get("clarification_question_text", "لطفاً اطلاعات بیشتری ارائه دهید.")
            response_keyboard_markup = reminder_ctx.get("clarification_keyboard_markup")
            logger.info(f"User {user_id}: Sending clarification question for status '{current_reminder_status}': '{response_text}'")

        elif current_reminder_status == "awaiting_confirmation":
            # This status is set by confirm_reminder_details_node, which also sets the question and keyboard.
            response_text = reminder_ctx.get("confirmation_question_text", "آیا تایید می‌کنید؟")
            response_keyboard_markup = reminder_ctx.get("confirmation_keyboard_markup")
            logger.info(f"User {user_id}: Sending confirmation question: '{response_text}'")

        elif current_reminder_status == "db_error":
            response_text = "متاسفانه در حال حاضر مشکلی در ذخیره یادآور شما پیش آمده. لطفاً کمی بعد دوباره تلاش کنید."
        elif current_reminder_status == "error_user_not_found" or current_reminder_status == "error_missing_user_id":
             response_text = "خطایی در شناسایی حساب کاربری شما رخ داده است. لطفا مجددا سعی کنید یا با /start دوباره شروع کنید."
        elif current_reminder_status == "error_missing_details_for_confirmation": # From confirm_reminder_details_node
            response_text = "خطای داخلی: اطلاعات کافی برای تایید یادآور موجود نیست. لطفا مجددا تلاش کنید."

    # --- B. Handle intents that directly lead to a response, or after specific actions --- 
    # This section handles intents that might not have a reminder_creation_status, or specific confirmed/cancelled actions.
    # It might overlap or be superseded by the status checks above if a status is set.
    
    elif intent == "intent_create_reminder_cancelled": # This is from determine_intent_node after user clicks NO on confirmation
        response_text = "ایجاد یادآور لغو شد."
        # reminder_creation_context should be cleared by determine_intent_node or the router for this path.

    elif intent == "intent_start_app": # Usually handled by execute_start_command_node; this is a fallback if routed here
        response_text = MSG_WELCOME # From config
        # Potentially add welcome keyboard if not already part of state from a dedicated start node
        if not state.get("response_keyboard_markup"): # Check if a start node already set it.
            response_keyboard_markup = {
                "type": "ReplyKeyboardMarkup",
                "keyboard": [
                    [{"text": "یادآورهای من"}, {"text": "راهنما"}],
                    [{"text": "پرداخت حق اشتراک"}],
                ],
                "resize_keyboard": True,
                "one_time_keyboard": False
            }

    elif intent == "intent_view_reminders":
        logger.info(f"Handling 'intent_view_reminders' for user {user_id}. Params: {params}")
        user_profile = state.get("user_profile")
        current_page = params.get("page", 1) # Get page from params (callback) or default to 1
        
        reminder_filters = state.get("reminder_filters", {})
        date_start_utc = reminder_filters.get("date_start_utc")
        date_end_utc = reminder_filters.get("date_end_utc")
        keywords = reminder_filters.get("keywords") 
        raw_date_phrase = reminder_filters.get("raw_date_phrase")

        filter_processing_message = state.get("filter_processing_status_message")
        
        response_text_parts = []
        if filter_processing_message:
            response_text_parts.append(filter_processing_message)

        applied_filter_descriptions = []
        if date_start_utc and date_end_utc:
            date_filter_desc = f"تاریخ: {raw_date_phrase}" if raw_date_phrase else f"تاریخ بین {date_start_utc.strftime('%Y-%m-%d')} و {date_end_utc.strftime('%Y-%m-%d')}"
            applied_filter_descriptions.append(date_filter_desc)
        if keywords and isinstance(keywords, list) and keywords:
            applied_filter_descriptions.append(f"کلیدواژه‌ها: {', '.join(keywords)}")

        if applied_filter_descriptions:
            response_text_parts.append(f"فیلترهای فعال: {'; '.join(applied_filter_descriptions)}.")


        if not user_profile or not user_profile.get("user_db_id"):
            response_text_parts.append("خطا: شناسه کاربری برای مشاهده یادآورها یافت نشد یا پروفایل بارگذاری نشده است.")
            logger.error(f"Cannot view reminders for user {user_id}: user_profile or user_db_id missing.")
        else:
            db: Session = next(get_db())
            try:
                user_db_id = user_profile["user_db_id"]
                reminders_per_page = settings.REMINDERS_PER_PAGE
                offset = (current_page - 1) * reminders_per_page

                query = db.query(Reminder).filter(
                    Reminder.user_db_id == user_db_id,
                    Reminder.is_active == True
                )
                count_query = db.query(func.count(Reminder.id)).filter(
                    Reminder.user_db_id == user_db_id,
                    Reminder.is_active == True
                )

                if date_start_utc and date_end_utc:
                    query = query.filter(Reminder.due_datetime_utc >= date_start_utc, Reminder.due_datetime_utc <= date_end_utc)
                    count_query = count_query.filter(Reminder.due_datetime_utc >= date_start_utc, Reminder.due_datetime_utc <= date_end_utc)
                
                if keywords and isinstance(keywords, list) and keywords:
                    keyword_filters_sql = [Reminder.task_description.ilike(f"%{k}%") for k in keywords]
                    query = query.filter(or_(*keyword_filters_sql))
                    count_query = count_query.filter(or_(*keyword_filters_sql))

                total_active_reminders_count = count_query.scalar() or 0
                total_pages = (total_active_reminders_count + reminders_per_page - 1) // reminders_per_page if reminders_per_page > 0 else 0
                
                active_reminders = []
                page_error_message = None

                if current_page < 1 or (total_pages > 0 and current_page > total_pages):
                    page_error_message = f"صفحه درخواستی ({current_page}) نامعتبر است. صفحات موجود از ۱ تا {total_pages if total_pages > 0 else 1} می‌باشد."
                elif total_active_reminders_count > 0 :
                     active_reminders = query.order_by(Reminder.due_datetime_utc.asc()).limit(reminders_per_page).offset(offset).all()
                
                if page_error_message:
                    response_text_parts.append(page_error_message)
                elif not active_reminders and total_active_reminders_count == 0:
                    if applied_filter_descriptions:
                        response_text_parts.append(settings.MSG_LIST_EMPTY_WITH_FILTERS)
                    else:
                        response_text_parts.append("شما در حال حاضر هیچ یادآور فعالی ندارید.")
                elif not active_reminders and total_active_reminders_count > 0 and not page_error_message : # Valid page, but no reminders (e.g. deleted)
                     response_text_parts.append(f"صفحه درخواستی ({current_page}) خالی است. ممکن است یادآورها اخیراً حذف شده باشند.")


                if active_reminders:
                    reminder_lines = [f"یادآورهای فعال (صفحه {current_page}/{total_pages}):"]
                    tehran_tz = pytz.timezone('Asia/Tehran')
                    for rem in active_reminders:
                        try:
                            due_tehran = rem.due_datetime_utc.astimezone(tehran_tz)
                            jalali_due = jdatetime.datetime.fromgregorian(datetime=due_tehran)
                            display_dt = jalali_due.strftime("%Y/%m/%d ساعت %H:%M")
                            reminder_lines.append(f"- «{rem.task_description}» در {display_dt} (ID: {rem.id})")
                        except Exception as e:
                            logger.error(f"Error formatting reminder ID {rem.id} for display (user {user_id}): {e}")
                            reminder_lines.append(f"- «{rem.task_description}» (خطا در نمایش زمان - ID: {rem.id})")
                    response_text_parts.append("\n".join(reminder_lines))

                    # Pagination and Clear Filters buttons
                    inline_keyboard_rows = []
                    pagination_buttons = []
                    if current_page > 1:
                        pagination_buttons.append({"text": f"⬅️ صفحه قبل ({current_page - 1})", "callback_data": f"view_reminders:page:{current_page - 1}"})
                    if current_page < total_pages:
                        pagination_buttons.append({"text": f"صفحه بعد ({current_page + 1}) ➡️", "callback_data": f"view_reminders:page:{current_page + 1}"})
                    
                    if pagination_buttons:
                        inline_keyboard_rows.append(pagination_buttons)
                    
                    if applied_filter_descriptions:
                        inline_keyboard_rows.append([{"text": "❌ پاک کردن فیلترها", "callback_data": "clear_filters_view_reminders:page:1"}])

                    if inline_keyboard_rows:
                        response_keyboard_markup = {"type": "InlineKeyboardMarkup", "inline_keyboard": inline_keyboard_rows}
                
                # If no active reminders and no filters applied, and it's page 1,
                # the "هیچ یادآور فعالی ندارید" message is already handled.
                # If filters are applied and no reminders, MSG_LIST_EMPTY_WITH_FILTERS is handled.

            except Exception as e:
                logger.error(f"Database error fetching reminders for user {user_id}, page {current_page}: {e}", exc_info=True)
                response_text_parts.append("متاسفانه مشکلی در دسترسی به یادآورهای شما پیش آمده است.")
            finally:
                if db: db.close()
        
        response_text = "\n".join(filter(None, response_text_parts)) # Join non-empty parts
        if not response_text: # Should not happen, but as a fallback
             response_text = "در حال حاضر اطلاعاتی برای نمایش وجود ندارد."

        state["active_reminders_page"] = current_page 

    elif intent == "intent_cancel_operation":
        response_text = "عملیات فعلی لغو شد."
        # reminder_creation_context should be cleared by determine_intent_node or router for this.
        # Here, we just provide the message.

    elif intent == "intent_show_privacy_policy":
        response_text = settings.MSG_PRIVACY_POLICY

    elif intent == "intent_help":
        response_text = settings.MSG_HELP # Use message from config
    elif intent == "intent_greeting":
        response_text = "سلام! چطور می‌توانم امروز به شما کمک کنم؟"
    elif intent == "intent_farewell":
        response_text = "خدانگهدار!"
    elif intent == "intent_affirmation":
        response_text = "متوجه شدم."
    elif intent == "intent_negation":
        response_text = "باشه."
    elif intent == "intent_clarification_needed": # When Gemini directly outputs this intent
        response_text = "متاسفانه منظور شما را کامل متوجه نشدم. می‌توانید واضح‌تر بگویید یا از دستور /cancel برای شروع مجدد استفاده کنید."
    elif intent == "unknown_intent" and params.get("error_in_nlu"):
        response_text = f"خطایی در پردازش زبان طبیعی درخواست شما رخ داد. لطفا دوباره تلاش کنید."
    elif intent == "unknown_intent":
        response_text = f"متاسفانه منظور شما از «{raw_input_text}» را متوجه نشدم. برای راهنمایی /help را ارسال کنید."


    ai_message_content = response_text # Ensure AIMessage uses the final response_text

    logger.info(f"User {user_id}: Response for intent='{intent}', status='{current_reminder_status}': '{response_text[:200]}...'")
    return {
        "response_text": response_text, 
        "response_keyboard_markup": response_keyboard_markup, # Pass through keyboard if set
        "current_node_name": "handle_intent_node",
        "messages": [AIMessage(content=ai_message_content)] # Add response to message history
    }

async def format_response_node(state: AgentState) -> Dict[str, Any]:
    """Node to format the final response. For now, it's a pass-through.
    If AIMessage was already added by handle_intent_node, this node might just confirm.
    Or, if response_text is the primary output, this node ensures it's clean.
    """
    logger.info(f"Graph: Entered format_response_node for user {state.get('user_id')}")
    response = state.get("response_text", "متاسفانه خطایی رخ داده است.")
    # If AIMessage was not added by the intent handling node (e.g. for unknown_intent direct route)
    # we should add it here.
    current_messages = state.get("messages", [])
    ai_message_to_add = AIMessage(content=response) # Default to creating it

    if current_messages:
        if isinstance(current_messages[-1], AIMessage) and current_messages[-1].content == response:
            logger.debug("format_response_node: AIMessage already present and matches response_text. No new message added.")
            # If last message is already an AIMessage with same content, no need to add again
            # However, the graph expects a dictionary with a 'messages' key if it's an output type.
            # So, we still return the existing messages.
            return {
                "response_text": response,
                "current_node_name": "format_response_node",
                "messages": current_messages # Return existing messages
            }
        else: # Different content or not an AIMessage, add new
            logger.debug(f"format_response_node adding new AIMessage: {ai_message_to_add}")
            # add_messages from AgentState will handle merging if 'messages' is already a list
            return {
                "response_text": response,
                "current_node_name": "format_response_node",
                "messages": [ai_message_to_add] # Return new message to be added/merged
            }
    else: # No messages yet, add this one
        logger.debug(f"format_response_node adding initial AIMessage: {ai_message_to_add}")
        return {
            "response_text": response,
            "current_node_name": "format_response_node",
            "messages": [ai_message_to_add]
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