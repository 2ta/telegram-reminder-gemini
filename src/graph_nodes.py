import logging
from typing import Dict, Any
from src.graph_state import AgentState
from langgraph.graph.message import AIMessage

logger = logging.getLogger(__name__)

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
    """Node to determine user intent (placeholder). Will later use NLU."""
    logger.info(f"Graph: Entered determine_intent_node for user {state.get('user_id')}")
    input_text = state.get("input_text", "").lower()
    intent = "unknown_intent"
    parameters = {}

    # Simple rule-based intent detection for now
    if "یادآوری کن" in input_text or "یادآور" in input_text:
        intent = "create_reminder_placeholder"
        # Basic parameter extraction placeholder
        parameters = {"raw_text": input_text}
    elif "سلام" in input_text or "وقت بخیر" in input_text:
        intent = "greeting"
    elif "کمک" in input_text or "راهنما" in input_text:
        intent = "help"
    # Add more rules as needed for basic commands or intents before full NLU

    logger.info(f"Determined intent: {intent} with params: {parameters}")
    return {
        "current_intent": intent,
        "extracted_parameters": parameters,
        "current_node_name": "determine_intent_node"
    }

async def handle_intent_node(state: AgentState) -> Dict[str, Any]:
    """Node to handle the determined intent (placeholder)."""
    logger.info(f"Graph: Entered handle_intent_node for user {state.get('user_id')}")
    intent = state.get("current_intent", "unknown_intent")
    params = state.get("extracted_parameters", {})
    response_text = "متوجه منظور شما نشدم. می‌توانید از دستور /help استفاده کنید."

    if intent == "create_reminder_placeholder":
        response_text = f"باشه، یادآور برای '{params.get('raw_text', '')}' تنظیم می‌شود (این یک placeholder است)."
    elif intent == "greeting":
        response_text = "سلام! چطور می‌توانم کمکتان کنم؟"
    elif intent == "help":
        response_text = "شما درخواست کمک کردید. برای لیست دستورات از /help استفاده کنید (پاسخ از گراف)."
    # More intent handling logic will go here

    logger.info(f"Response for intent '{intent}': '{response_text}'")
    # Also prepare an AIMessage for history
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
    # If AIMessage was not added by the intent handling node (e.g. for unknown_intent direct route)
    # we should add it here.
    current_messages = state.get("messages", [])
    if not current_messages or not isinstance(current_messages[-1], AIMessage) or current_messages[-1].content != response:
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
    if intent == "unknown_intent":
        logger.info("Routing to handle_intent_node for unknown_intent (will generate default response).")
        # Even unknown intent goes to handle_intent_node which then formulates a default unknown message.
        # This ensures AIMessage is consistently added.
        return "handle_intent_node" 
    logger.info(f"Routing to handle_intent_node for intent: {intent}")
    return "handle_intent_node" 