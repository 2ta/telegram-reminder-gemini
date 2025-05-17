import logging
from langgraph.graph import StateGraph, END

from src.graph_state import AgentState
from src.graph_nodes import (
    entry_node,
    load_user_profile_node,
    determine_intent_node,
    process_datetime_node,
    validate_and_clarify_reminder_node,
    confirm_reminder_details_node,
    create_reminder_node,
    handle_intent_node,
    format_response_node
)

logger = logging.getLogger(__name__)

# --- Conditional Edges (Router functions) ---

def route_after_intent_determination(state: AgentState):
    """Router function after intent determination, directing to various flows."""
    intent = state.get("current_intent")
    reminder_ctx = state.get("reminder_creation_context", {})
    user_id = state.get("user_id")
    logger.info(f"Router (after_intent_determination) for user {user_id}: Intent='{intent}'")

    if intent == "intent_create_reminder":
        # If NLU picked up task and datetime in the first go, and they are already processed (e.g. from a loop-back after clarification)
        # This check might be too simplistic; process_datetime and validate_and_clarify should handle it robustly.
        # For now, always go to process_datetime first for intent_create_reminder to ensure data is in context.
        logger.info(f"Routing '{intent}' to process_datetime_node.")
        return "process_datetime_node"
    
    elif intent == "intent_create_reminder_confirmed":
        logger.info(f"Routing '{intent}' to create_reminder_node.")
        return "create_reminder_node"
        
    elif intent == "intent_create_reminder_cancelled":
        logger.info(f"Routing '{intent}' (cancelled) to handle_intent_node for feedback.")
        return "handle_intent_node" # To give cancellation feedback
        
    elif intent in ["intent_start_app", "intent_help", "intent_show_privacy_policy", "intent_view_reminders", "intent_payment_initiate", "intent_cancel_operation", "intent_greeting", "intent_farewell", "intent_affirmation", "intent_negation", "unknown_intent", "intent_clarification_needed", "intent_payment_callback_process"]:
        # Most other intents go directly to handle_intent_node to formulate a response or execute simple actions.
        logger.info(f"Routing '{intent}' to handle_intent_node.")
        return "handle_intent_node"
        
    # Fallback: if an intent isn't explicitly routed, it goes to handle_intent for a generic response.
    logger.warning(f"Intent '{intent}' has no explicit route in route_after_intent_determination. Defaulting to handle_intent_node.")
    return "handle_intent_node"

def route_after_validation_and_clarification(state: AgentState):
    """Router function after validation and clarification. Determines next step based on status."""
    user_id = state.get("user_id")
    # Get status from within the reminder_creation_context
    reminder_ctx = state.get("reminder_creation_context", {})
    creation_status = reminder_ctx.get("status") 

    logger.info(f"Router (after_validation_and_clarification) for user {user_id}: Status from context='{creation_status}'")

    if creation_status == "ready_for_confirmation":
        logger.info(f"Routing user {user_id} to confirm_reminder_details_node.")
        return "confirm_reminder_details_node"
    elif creation_status and ("clarification_needed" in creation_status or "error_limit_exceeded" in creation_status):
        # This includes: clarification_needed_task, clarification_needed_datetime, error_limit_exceeded
        # handle_intent_node will use the question/message set in reminder_creation_context by validate_and_clarify_reminder_node
        logger.info(f"Clarification needed or limit error ('{creation_status}'). Routing to handle_intent_node to inform user.")
        return "handle_intent_node" # Graph will end, user provides clarification, then re-enters graph.
    else:
        # Fallback if status is unexpected, or if no clarification was needed but not ready for confirmation (should not happen ideally)
        logger.warning(f"Unexpected status '{creation_status}' after validation/clarification. Defaulting to handle_intent_node.")
        return "handle_intent_node"

def create_graph():
    """Creates and compiles the LangGraph for the reminder bot."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("entry_node", entry_node)
    workflow.add_node("load_user_profile_node", load_user_profile_node)
    workflow.add_node("determine_intent_node", determine_intent_node) # Updated node
    workflow.add_node("process_datetime_node", process_datetime_node) # Updated node
    workflow.add_node("validate_and_clarify_reminder_node", validate_and_clarify_reminder_node) # New node
    workflow.add_node("confirm_reminder_details_node", confirm_reminder_details_node)       # New node
    workflow.add_node("create_reminder_node", create_reminder_node)   # Updated node
    workflow.add_node("handle_intent_node", handle_intent_node)     # Updated node
    workflow.add_node("format_response_node", format_response_node)

    # Set entry point
    workflow.set_entry_point("entry_node")

    # --- Define Edges ---
    workflow.add_edge("entry_node", "load_user_profile_node")
    workflow.add_edge("load_user_profile_node", "determine_intent_node")
    
    # Routing after intent is determined
    workflow.add_conditional_edges(
        "determine_intent_node",
        route_after_intent_determination,
        {
            "process_datetime_node": "process_datetime_node", # For intent_create_reminder
            "create_reminder_node": "create_reminder_node",   # For intent_create_reminder_confirmed
            "handle_intent_node": "handle_intent_node"      # For all other intents, cancellations, or direct responses
        }
    )

    # After processing datetime (if on create_reminder path)
    workflow.add_edge("process_datetime_node", "validate_and_clarify_reminder_node")

    # Routing after validation and clarification setup
    workflow.add_conditional_edges(
        "validate_and_clarify_reminder_node",
        route_after_validation_and_clarification,
        {
            "confirm_reminder_details_node": "confirm_reminder_details_node", # If ready for confirmation
            "handle_intent_node": "handle_intent_node"                   # If clarification needed or limit error (ends graph for user input)
        }
    )

    # After confirm_reminder_details_node, the graph should send the confirmation prompt and then END, awaiting user's callback.
    # The callback (yes/no) will re-enter the graph, determine_intent_node will catch it and route to create_reminder_node or handle_intent_node.
    workflow.add_edge("confirm_reminder_details_node", "format_response_node")

    # After actual reminder creation (or failure like DB error during creation)
    workflow.add_edge("create_reminder_node", "handle_intent_node") # To send success/failure message
    
    # Final response formatting and end
    workflow.add_edge("handle_intent_node", "format_response_node")
    workflow.add_edge("format_response_node", END)

    # Explicitly compile without a checkpointer
    app = workflow.compile(checkpointer=None)
    logger.info("LangGraph app compiled successfully (checkpointing explicitly disabled with checkpointer=None).")
    return app

# Singleton instance of the graph
lang_graph_app = create_graph()

if __name__ == '__main__':
    import os
    os.makedirs("./checkpoints", exist_ok=True)
    from src.logging_config import setup_logging
    setup_logging()
    
    # Test basic execution without full scenarios
    test_input = {
        "input_text": "/start",
        "user_id": "test_user",
        "chat_id": "test_chat",
        "message_type": "command",
        "user_telegram_details": {"first_name": "Tester", "username": "tester"}
    }
    
    logger.info("Testing basic LangGraph execution...")
    result = lang_graph_app.invoke(test_input)
    logger.info(f"Test result (START command): {result.get('response_text')}")