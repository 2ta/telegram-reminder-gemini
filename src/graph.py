import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver # Example checkpoint saver

from src.graph_state import AgentState
from src.graph_nodes import (
    entry_node,
    determine_intent_node,
    extract_parameters_node,
    handle_intent_node,
    format_response_node,
    route_after_intent_determination
)

logger = logging.getLogger(__name__)

def create_graph():
    """Creates and compiles the LangGraph for the reminder bot."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("entry_node", entry_node)
    workflow.add_node("determine_intent_node", determine_intent_node)
    workflow.add_node("extract_parameters_node", extract_parameters_node)
    workflow.add_node("handle_intent_node", handle_intent_node)
    workflow.add_node("format_response_node", format_response_node)

    # Set entry point
    workflow.set_entry_point("entry_node")

    # Add edges
    workflow.add_edge("entry_node", "determine_intent_node")
    
    # Conditional edge after intent determination
    workflow.add_conditional_edges(
        "determine_intent_node",
        route_after_intent_determination, 
        {
            "extract_parameters_node": "extract_parameters_node",
            "handle_intent_node": "handle_intent_node"
        }
    )
    
    # Edge from parameter extraction to intent handling
    workflow.add_edge("extract_parameters_node", "handle_intent_node")

    workflow.add_edge("handle_intent_node", "format_response_node")
    workflow.add_edge("format_response_node", END)

    # Memory for checkpoints
    # Ensure the directory for the SQLite DB exists.
    # For production, consider a more robust checkpoint solution (e.g., Redis, Postgres).
    memory = SqliteSaver.from_conn_string("sqlite:///./checkpoints/langgraph_checkpoints.db")

    # Compile the graph
    app = workflow.compile(checkpointer=memory)
    logger.info("LangGraph app compiled successfully.")
    return app

# Singleton instance of the graph
lang_graph_app = create_graph()

if __name__ == '__main__':
    # Ensure the checkpoints directory exists for the SQLite DB before graph creation
    import os
    os.makedirs("./checkpoints", exist_ok=True)

    from src.logging_config import setup_logging
    setup_logging()

    logger.info("Testing LangGraph app execution with NLU integration...")
    
    # Test Case 1: Create Reminder
    config_reminder = {"configurable": {"thread_id": "user_123_conv_nlu_reminder_1"}}
    initial_input_reminder = {
        "input_text": "یادآوری کن فردا ساعت ۱۰ صبح جلسه مهمی با مدیرعامل دارم",
        "user_id": 123,
        "message_type": "text",
        "messages": [] 
    }

    logger.info(f"\nInvoking graph for reminder input: '{initial_input_reminder['input_text']}'")
    # Ensure GEMINI_API_KEY is set in .env for this test to hit the actual LLM
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. LLM calls in graph will fail. Skipping live invoke.")
    else:
        final_state_reminder = lang_graph_app.invoke(initial_input_reminder, config=config_reminder)
        logger.info(f"Graph execution finished. Final state for '{config_reminder['configurable']['thread_id']}':")
        logger.info(f"  Input: {initial_input_reminder.get('input_text')}")
        logger.info(f"  Intent: {final_state_reminder.get('current_intent')}")
        logger.info(f"  Parameters: {final_state_reminder.get('extracted_parameters')}")
        logger.info(f"  Response: {final_state_reminder.get('response_text')}")
        logger.info(f"  Message History: {final_state_reminder.get('messages')}")

    # Test Case 2: Greeting
    config_greeting = {"configurable": {"thread_id": "user_456_conv_nlu_greeting_1"}}
    initial_input_greeting = {
        "input_text": "سلام خوبی؟",
        "user_id": 456,
        "message_type": "text",
        "messages": []
    }
    logger.info(f"\nInvoking graph for greeting input: '{initial_input_greeting['input_text']}'")
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. LLM calls in graph will fail. Skipping live invoke.")
    else:
        final_state_greeting = lang_graph_app.invoke(initial_input_greeting, config=config_greeting)
        logger.info(f"Graph execution finished. Final state for '{config_greeting['configurable']['thread_id']}':")
        logger.info(f"  Input: {initial_input_greeting.get('input_text')}")
        logger.info(f"  Intent: {final_state_greeting.get('current_intent')}")
        logger.info(f"  Parameters: {final_state_greeting.get('extracted_parameters')}")
        logger.info(f"  Response: {final_state_greeting.get('response_text')}")
        logger.info(f"  Message History: {final_state_greeting.get('messages')}")

    # Test Case 3: Unknown/Complex query that might not fit easily
    config_unknown = {"configurable": {"thread_id": "user_789_conv_nlu_unknown_1"}}
    initial_input_unknown = {
        "input_text": "نظرت در مورد هوش مصنوعی چیه؟",
        "user_id": 789,
        "message_type": "text",
        "messages": []
    }
    logger.info(f"\nInvoking graph for unknown input: '{initial_input_unknown['input_text']}'")
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. LLM calls in graph will fail. Skipping live invoke.")
    else:
        final_state_unknown = lang_graph_app.invoke(initial_input_unknown, config=config_unknown)
        logger.info(f"Graph execution finished. Final state for '{config_unknown['configurable']['thread_id']}':")
        logger.info(f"  Input: {initial_input_unknown.get('input_text')}")
        logger.info(f"  Intent: {final_state_unknown.get('current_intent')}") # Expected UNKNOWN
        logger.info(f"  Parameters: {final_state_unknown.get('extracted_parameters')}")
        logger.info(f"  Response: {final_state_unknown.get('response_text')}")
        logger.info(f"  Message History: {final_state_unknown.get('messages')}") 