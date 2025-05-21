import logging
from langgraph.graph import StateGraph, END
import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

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
    format_response_node,
    execute_start_command_node
)

logger = logging.getLogger(__name__)

# --- Conditional Edges (Router functions) ---

def route_after_intent_determination(state: AgentState):
    """Routes to specific nodes based on determined intent."""
    intent = state.get("current_intent", "unknown_intent")
    logger.info(f"Router (after_intent_determination) for user {state.get('user_id')}: Intent='{intent}'")

    if intent == "intent_start":
        logger.info(f"Routing '{intent}' to execute_start_command_node.")
        return "execute_start_command_node"
    elif intent == "intent_create_reminder":
        return "process_datetime_node" # First step in reminder creation flow
    elif intent == "intent_create_reminder_confirmed":
        return "create_reminder_node" # When user confirms creating the reminder
    elif intent == "intent_create_reminder_cancelled":
        # When user cancels, clean up context and send to handle_intent_node for cancellation msg
        return "handle_intent_node"

    # All other intents go to handle_intent_node
    logger.info(f"Routing '{intent}' to handle_intent_node (default).")
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
    workflow.add_node("determine_intent_node", determine_intent_node)
    workflow.add_node("execute_start_command_node", execute_start_command_node)
    workflow.add_node("process_datetime_node", process_datetime_node)
    workflow.add_node("validate_and_clarify_reminder_node", validate_and_clarify_reminder_node)
    workflow.add_node("confirm_reminder_details_node", confirm_reminder_details_node)
    workflow.add_node("create_reminder_node", create_reminder_node)
    workflow.add_node("handle_intent_node", handle_intent_node)
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
            "execute_start_command_node": "execute_start_command_node",
            "process_datetime_node": "process_datetime_node",
            "create_reminder_node": "create_reminder_node",
            "handle_intent_node": "handle_intent_node"
        }
    )

    # After processing datetime (if on create_reminder path)
    workflow.add_edge("process_datetime_node", "validate_and_clarify_reminder_node")

    # Routing after validation and clarification setup
    workflow.add_conditional_edges(
        "validate_and_clarify_reminder_node",
        route_after_validation_and_clarification,
        {
            "confirm_reminder_details_node": "confirm_reminder_details_node",
            "handle_intent_node": "handle_intent_node"
        }
    )

    # After confirm_reminder_details_node, the graph should send the confirmation prompt and then END, awaiting user's callback.
    # The callback (yes/no) will re-enter the graph, determine_intent_node will catch it and route to create_reminder_node or handle_intent_node.
    workflow.add_edge("confirm_reminder_details_node", "format_response_node")
    
    workflow.add_edge("execute_start_command_node", "format_response_node")

    # After actual reminder creation (or failure like DB error during creation)
    workflow.add_edge("create_reminder_node", "handle_intent_node") # To send success/failure message
    
    # Final response formatting and end
    workflow.add_edge("handle_intent_node", "format_response_node")
    workflow.add_edge("format_response_node", END)

    # For now, let's compile without a checkpointer to at least make the bot functional
    # We can add a proper checkpointer later when we have more time to debug the issue
    app = workflow.compile()
    logger.info("LangGraph app compiled successfully (without checkpointing).")
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
    
    async def test_async():
        result = await lang_graph_app.ainvoke(test_input)
        logger.info(f"Test result (START command): {result.get('response_text')}")
    
    # Run the async test
    asyncio.run(test_async())