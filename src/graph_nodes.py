import logging
from typing import Dict, Any, List
from src.graph_state import AgentState
from langgraph.graph.message import AIMessage, HumanMessage

# LLM Utilities and Prompts
from src.llm_utils import get_llm_json_response
from resources.prompts import INTENT_DETECTION_PROMPT_TEMPLATE, PARAMETER_EXTRACTION_PROMPT_REMINDER
from config.config import settings

logger = logging.getLogger(__name__)

# Helper to format message history for the prompt
def format_message_history_for_prompt(messages: List[Any], max_messages: int = 5) -> str:
    if not messages:
        return "None"
    
    # Take the last N messages
    recent_messages = messages[-max_messages:]
    formatted_history = []
    for msg in recent_messages:
        if isinstance(msg, HumanMessage):
            formatted_history.append(f"کاربر: {msg.content}")
        elif isinstance(msg, AIMessage):
            formatted_history.append(f"دستیار: {msg.content}")
        # Could add other message types if they exist in the state's messages
    
    return "\n".join(formatted_history) if formatted_history else "None"

async def entry_node(state: AgentState) -> Dict[str, Any]:
    """Node that processes the initial input and determines message type."""
    logger.info(f"Graph: Entered entry_node for user {state.get('user_id')}")
    current_input = state.get("input_text", "")
    # For now, we assume message_type is pre-determined before graph invocation
    # or set by the component that calls the graph.
    # This node could enhance that if needed.
    message_type = state.get("message_type", "unknown")
    logger.info(f"Input: '{current_input}', Type: {message_type}")
    
    # This node could potentially route to different initial processing based on type
    # For now, it's a simple pass-through or basic logging.
    return {"current_node_name": "entry_node"}

async def determine_intent_node(state: AgentState) -> Dict[str, Any]:
    """Node to determine user intent using NLU (LLM call)."""
    logger.info(f"Graph: Entered determine_intent_node for user {state.get('user_id')}")
    input_text = state.get("input_text", "")
    messages_history = state.get("messages", [])

    # Format history for the prompt
    formatted_history = format_message_history_for_prompt(messages_history)

    intent = "unknown"
    parameters = {}

    if not input_text.strip():
        logger.warning("Input text is empty, cannot determine intent.")
        return {
            "current_intent": intent,
            "extracted_parameters": parameters,
            "current_node_name": "determine_intent_node"
        }

    try:
        prompt_input_vars = {
            "user_input": input_text,
            "user_history": formatted_history 
        }
        llm_response = await get_llm_json_response(
            prompt_template=INTENT_DETECTION_PROMPT_TEMPLATE,
            input_variables=prompt_input_vars,
        )
        
        if llm_response and "intent" in llm_response:
            intent = llm_response["intent"]
            logger.info(f"LLM determined intent: {intent} for input: '{input_text}'")
        else:
            logger.warning(f"LLM response for intent detection was missing 'intent' field or was empty. Response: {llm_response}")
            intent = "unknown"

    except ValueError as ve:
        logger.error(f"ValueError during intent detection LLM call: {ve}. Input: '{input_text}'")
        intent = "unknown"
    except Exception as e:
        logger.error(f"Exception during intent detection LLM call: {e}. Input: '{input_text}'")
        intent = "unknown"

    logger.info(f"Final determined intent: {intent}")
    return {
        "current_intent": intent,
        "extracted_parameters": parameters,
        "current_node_name": "determine_intent_node"
    }

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Node to handle the determined intent (placeholder)."""
    logger.info(f"Graph: Entered handle_intent_node for user {state.get('user_id')}")
    intent = state.get("current_intent", "unknown")
    params = state.get("extracted_parameters", {})
    response_text = "متوجه منظور شما نشدم. می‌توانید از دستور /help استفاده کنید."

    if intent == "CREATE_REMINDER":
        task = params.get("task", "چیزی که مشخص نکردید")
        date_str = params.get("date_str", "زمانی نامشخص")
        time_str = params.get("time_str", "")
        
        response_text = f"قصد شما برای ایجاد یادآور دریافت شد. جزئیات اولیه: وظیفه='{task}', تاریخ='{date_str}', زمان='{time_str}'. در حال پردازش بیشتر..."
    elif intent == "GREETING":
        response_text = "سلام! چطور می‌توانم کمکتان کنم؟"
    elif intent == "HELP":
        response_text = "شما درخواست کمک کردید. برای لیست دستورات از /help استفاده کنید (پاسخ از گراف)."
    elif intent == "VIEW_REMINDERS":
        response_text = "درخواست شما برای مشاهده یادآورها دریافت شد. (این قابلیت به زودی اضافه خواهد شد)."
    elif intent == "UNKNOWN":
        response_text = "متوجه منظور شما نشدم. لطفا واضح‌تر بگویید یا از /help برای راهنمایی استفاده کنید."
    # More intent handling logic will go here

    logger.info(f"Response for intent '{intent}': '{response_text}'")
    return {
        "response_text": response_text, 
        "current_node_name": "handle_intent_node",
        "messages": [AIMessage(content=response_text)]
    }

async def format_response_node(state: AgentState) -> Dict[str, Any]:
    """Node to format the final response. For now, it's a pass-through.
    If AIMessage was already added by handle_intent_node, this node might just confirm.
    Or, if response_text is the primary output, this node ensures it's clean.
    """
    logger.info(f"Graph: Entered format_response_node for user {state.get('user_id')}")
    response = state.get("response_text", "متاسفانه خطایی رخ داده است.")
    current_messages = state.get("messages", [])
    last_message_is_matching_ai = False
    if current_messages and isinstance(current_messages[-1], AIMessage):
        if current_messages[-1].content == response:
            last_message_is_matching_ai = True
    
    if not last_message_is_matching_ai:
        ai_message_to_add = AIMessage(content=response)
        logger.debug(f"format_response_node adding AIMessage: {ai_message_to_add}")
        return {
            "response_text": response, 
            "current_node_name": "format_response_node",
            "messages": [ai_message_to_add]
        }
    
    return {"response_text": response, "current_node_name": "format_response_node"}

# Conditional Edges (Router functions)
def route_after_intent_determination(state: AgentState):
    """Router function to decide next step after intent determination."""
    intent = state.get("current_intent")
    logger.info(f"Routing based on intent: {intent}")

    if intent == "CREATE_REMINDER":
        return "extract_parameters_node"
    elif intent in ["GREETING", "HELP", "VIEW_REMINDERS", "UNKNOWN", "AFFIRM", "DENY", "THANK_YOU", "GOODBYE"]:
        return "handle_intent_node"
    else:
        logger.warning(f"Unknown intent '{intent}' encountered in router. Defaulting to handle_intent_node.")
        return "handle_intent_node"

# Placeholder for the new node - will be implemented in the next step
async def extract_parameters_node(state: AgentState) -> Dict[str, Any]:
    logger.info(f"Graph: Entered extract_parameters_node for user {state.get('user_id')}")
    input_text = state.get("input_text", "")
    current_intent = state.get("current_intent")

    extracted_params = {"task": None, "date_str": None, "time_str": None} # Initialize with expected keys

    if current_intent != "CREATE_REMINDER" or not input_text.strip():
        logger.warning(
            f"Skipping parameter extraction: intent is not CREATE_REMINDER ('{current_intent}') or input text is empty."
        )
        return {"extracted_parameters": state.get("extracted_parameters", extracted_params), "current_node_name": "extract_parameters_node"}

    try:
        prompt_input_vars = {"user_input": input_text}
        llm_response = await get_llm_json_response(
            prompt_template=PARAMETER_EXTRACTION_PROMPT_REMINDER,
            input_variables=prompt_input_vars,
            # model_name=settings.PARAM_EXTRACTION_MODEL_NAME # If specific model needed
        )

        if llm_response:
            task = llm_response.get("task")
            date_str = llm_response.get("date") # Raw date string from LLM
            time_str = llm_response.get("time") # Raw time string from LLM
            
            if task: # Task is mandatory for a reminder
                extracted_params["task"] = task
                extracted_params["date_str"] = date_str # Store as str, normalization is next step
                extracted_params["time_str"] = time_str # Store as str, normalization is next step
                logger.info(f"LLM extracted parameters: Task='{task}', DateStr='{date_str}', TimeStr='{time_str}'")
            else:
                logger.warning(f"LLM parameter extraction did not return a 'task'. Response: {llm_response}")
                # Fallback: use full input as task if LLM fails to find a specific one
                extracted_params["task"] = input_text 
        else:
            logger.warning(f"LLM response for parameter extraction was empty. Input: '{input_text}'")
            extracted_params["task"] = input_text # Fallback

    except ValueError as ve: # JSON parsing or API key issues
        logger.error(f"ValueError during parameter extraction LLM call: {ve}. Input: '{input_text}'")
        extracted_params["task"] = input_text # Fallback
    except Exception as e:
        logger.error(f"Exception during parameter extraction LLM call: {e}. Input: '{input_text}'")
        extracted_params["task"] = input_text # Fallback

    return {
        "extracted_parameters": extracted_params,
        "current_node_name": "extract_parameters_node"
    } 