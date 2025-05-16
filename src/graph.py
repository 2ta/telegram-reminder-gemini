import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

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
    """Router after reminder parameters have been validated or clarification has been set up."""
    user_id = state.get("user_id")
    # reminder_creation_status is set by validate_and_clarify_reminder_node
    creation_status = state.get("reminder_creation_status") 
    logger.info(f"Router (after_validation_and_clarification) for user {user_id}: Status='{creation_status}'")

    if creation_status == "ready_for_confirmation":
        logger.info("Details ready for confirmation. Routing to confirm_reminder_details_node.")
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

    # After confirm_reminder_details_node, the graph should effectively end to await user's callback.
    # handle_intent_node will be responsible for sending the confirmation message with buttons.
    # The callback (yes/no) will re-enter the graph, determine_intent_node will catch it and route to create_reminder_node or handle_intent_node.
    workflow.add_edge("confirm_reminder_details_node", "handle_intent_node") 
    # This ensures the confirmation message is sent. The `pending_confirmation` state is key here.

    # After actual reminder creation (or failure like DB error during creation)
    workflow.add_edge("create_reminder_node", "handle_intent_node") # To send success/failure message
    
    # Final response formatting and end
    workflow.add_edge("handle_intent_node", "format_response_node")
    workflow.add_edge("format_response_node", END)

    # Memory for checkpoints
    memory = SqliteSaver.from_conn_string("sqlite:///./checkpoints/langgraph_checkpoints.db")
    app = workflow.compile(checkpointer=memory)
    logger.info("LangGraph app compiled successfully with new reminder creation flow.")
    return app

# Singleton instance of the graph
lang_graph_app = create_graph()

if __name__ == '__main__':
    import os
    os.makedirs("./checkpoints", exist_ok=True)
    from src.logging_config import setup_logging
    setup_logging()
    logger.info("Testing LangGraph app execution (Reminder Creation Flow Focus)...")

    # --- Test Scenario 1: Full initial input ---
    config_user1 = {"configurable": {"thread_id": "user_reminder_test_1"}}
    initial_input_full = {
        "input_text": "یادآوری کن فردا ساعت ۲ بعد از ظهر جلسه تیم",
        "user_id": "test_user_full",
        "chat_id": "chat_full",
        "message_type": "text",
        "user_telegram_details": {"first_name": "TestFull", "username": "testfulluser"} # For user creation if needed
    }
    # To clear previous state for this thread_id (for clean test run):
    # current_state = lang_graph_app.get_state(config_user1)
    # if current_state:
    #     logger.info(f"Previous state found for {config_user1['configurable']['thread_id']}, messages: {len(current_state.messages)}")
        # lang_graph_app.update_state(config_user1, None) # This would clear, but be careful
        # A better way is to use unique thread_ids for each test run if full reset is needed, or handle state accumulation.

    logger.info(f"\n--- Invoking graph for: {initial_input_full['input_text']} ---")
    final_state_1 = lang_graph_app.invoke(initial_input_full, config=config_user1)
    logger.info(f"Graph run 1 (full initial) - User: {initial_input_full['user_id']}")
    logger.info(f"  Intent: {final_state_1.get('current_intent')}")
    logger.info(f"  Reminder Context: {final_state_1.get('reminder_creation_context')}")
    logger.info(f"  Pending Confirmation: {final_state_1.get('pending_confirmation')}")
    logger.info(f"  Response Text: {final_state_1.get('response_text')}")
    logger.info(f"  Keyboard: {final_state_1.get('response_keyboard_markup')}")
    logger.info(f"  Creation Status: {final_state_1.get('reminder_creation_status')}")

    # --- Test Scenario 2: User confirms (simulated callback) ---
    if final_state_1.get("pending_confirmation") == "create_reminder":
        confirm_input = {
            "input_text": "confirm_create_reminder:yes", # Simulating callback data
            "user_id": "test_user_full",
            "chat_id": "chat_full",
            "message_type": "callback_query"
        }
        logger.info(f"\n--- Invoking graph for confirmation: {confirm_input['input_text']} ---")
        final_state_2 = lang_graph_app.invoke(confirm_input, config=config_user1) # Same thread_id
        logger.info(f"Graph run 2 (confirmation) - User: {confirm_input['user_id']}")
        logger.info(f"  Intent: {final_state_2.get('current_intent')}")
        logger.info(f"  Reminder Context: {final_state_2.get('reminder_creation_context')}")
        logger.info(f"  Pending Confirmation: {final_state_2.get('pending_confirmation')}")
        logger.info(f"  Response Text: {final_state_2.get('response_text')}")
        logger.info(f"  Creation Status: {final_state_2.get('reminder_creation_status')}")

    # --- Test Scenario 3: Task missing initially ---
    config_user2 = {"configurable": {"thread_id": "user_reminder_test_2"}}
    initial_input_no_task = {
        "input_text": "یادآوری کن", # No task
        "user_id": "test_user_no_task",
        "chat_id": "chat_no_task",
        "message_type": "text",
        "user_telegram_details": {"first_name": "TestNoTask"}
    }
    logger.info(f"\n--- Invoking graph for: {initial_input_no_task['input_text']} ---")
    state_no_task_1 = lang_graph_app.invoke(initial_input_no_task, config=config_user2)
    logger.info(f"Graph run 3.1 (no task initial) - User: {initial_input_no_task['user_id']}")
    logger.info(f"  Response Text: {state_no_task_1.get('response_text')}")
    logger.info(f"  Reminder Context: {state_no_task_1.get('reminder_creation_context')}")
    logger.info(f"  Creation Status: {state_no_task_1.get('reminder_creation_status')}")

    # --- Test Scenario 3.2: User provides task ---
    if state_no_task_1.get("reminder_creation_context", {}).get("pending_clarification_type") == "task":
        provide_task_input = {
            "input_text": "خرید بلیط سینما",
            "user_id": "test_user_no_task",
            "chat_id": "chat_no_task",
            "message_type": "text"
        }
        logger.info(f"\n--- Invoking graph for providing task: {provide_task_input['input_text']} ---")
        state_no_task_2 = lang_graph_app.invoke(provide_task_input, config=config_user2)
        logger.info(f"Graph run 3.2 (provided task) - User: {provide_task_input['user_id']}")
        logger.info(f"  Response Text: {state_no_task_2.get('response_text')}") # Should ask for datetime
        logger.info(f"  Reminder Context: {state_no_task_2.get('reminder_creation_context')}")
        logger.info(f"  Creation Status: {state_no_task_2.get('reminder_creation_status')}")

        # --- Test Scenario 3.3: User provides datetime ---
        if state_no_task_2.get("reminder_creation_context", {}).get("pending_clarification_type") == "datetime":
            provide_datetime_input = {
                "input_text": "پس فردا ساعت ۷ غروب",
                "user_id": "test_user_no_task",
                "chat_id": "chat_no_task",
                "message_type": "text"
            }
            logger.info(f"\n--- Invoking graph for providing datetime: {provide_datetime_input['input_text']} ---")
            state_no_task_3 = lang_graph_app.invoke(provide_datetime_input, config=config_user2)
            logger.info(f"Graph run 3.3 (provided datetime) - User: {provide_datetime_input['user_id']}")
            logger.info(f"  Response Text: {state_no_task_3.get('response_text')}") # Should be confirmation q
            logger.info(f"  Keyboard: {state_no_task_3.get('response_keyboard_markup')}")
            logger.info(f"  Pending Confirmation: {state_no_task_3.get('pending_confirmation')}")
            logger.info(f"  Reminder Context: {state_no_task_3.get('reminder_creation_context')}")
            logger.info(f"  Creation Status: {state_no_task_3.get('reminder_creation_status')}")

            # --- Test Scenario 3.4: User confirms final details ---
            if state_no_task_3.get("pending_confirmation") == "create_reminder":
                confirm_final_input = {
                    "input_text": "confirm_create_reminder:yes",
                    "user_id": "test_user_no_task",
                    "chat_id": "chat_no_task",
                    "message_type": "callback_query"
                }
                logger.info(f"\n--- Invoking graph for final confirmation: {confirm_final_input['input_text']} ---")
                state_no_task_4 = lang_graph_app.invoke(confirm_final_input, config=config_user2)
                logger.info(f"Graph run 3.4 (final confirmation) - User: {confirm_final_input['user_id']}")
                logger.info(f"  Response Text: {state_no_task_4.get('response_text')}") # Success message
                logger.info(f"  Reminder Context: {state_no_task_4.get('reminder_creation_context')}")
                logger.info(f"  Creation Status: {state_no_task_4.get('reminder_creation_status')}")

    logger.info("\n--- LangGraph testing completed. Check logs for details. ---")