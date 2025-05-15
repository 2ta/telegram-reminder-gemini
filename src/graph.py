import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver # Example checkpoint saver

from src.graph_state import AgentState
from src.graph_nodes import (
    entry_node,
    determine_intent_node,
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
    workflow.add_node("handle_intent_node", handle_intent_node)
    workflow.add_node("format_response_node", format_response_node)

    # Set entry point
    workflow.set_entry_point("entry_node")

    # Add edges
    workflow.add_edge("entry_node", "determine_intent_node")
    
    # Conditional edge after intent determination
    # Since route_after_intent_determination now always returns "handle_intent_node",
    # this simplifies to a direct edge, or the conditional can be kept if future states are added.
    # For now, let's make it explicit based on the router's current simple logic.
    workflow.add_conditional_edges(
        "determine_intent_node",
        route_after_intent_determination, # This function will always return "handle_intent_node"
        {
            "handle_intent_node": "handle_intent_node"
            # No other paths currently from this router
        }
    )
    # An alternative simpler way if the router *only* ever goes to one place for now:
    # workflow.add_edge("determine_intent_node", "handle_intent_node")
    
    workflow.add_edge("handle_intent_node", "format_response_node")
    workflow.add_edge("format_response_node", END)

    # Memory for checkpoints (example using SQLite)
    # This allows the graph to be stateful across multiple invocations for the same user/conversation.
    # Ensure the directory for the SQLite DB exists.
    # For production, consider a more robust checkpoint solution (e.g., Redis, Postgres).
    memory = SqliteSaver.from_conn_string("sqlite:///./checkpoints/langgraph_checkpoints.db")

    # Compile the graph
    # Checkpointer is crucial for `add_messages` in AgentState to work across invocations.
    app = workflow.compile(checkpointer=memory)
    logger.info("LangGraph app compiled successfully.")
    return app

# Singleton instance of the graph
# This ensures the graph is compiled only once.
lang_graph_app = create_graph()

if __name__ == '__main__':
    # Ensure the checkpoints directory exists for the SQLite DB before graph creation
    import os
    os.makedirs("./checkpoints", exist_ok=True)

    from src.logging_config import setup_logging
    setup_logging()

    logger.info("Testing LangGraph app execution...")
    
    # Example initial state for a new conversation
    config = {"configurable": {"thread_id": "user_123_conv_1"}}
    initial_input = {
        "input_text": "سلام یادآوری کن فردا ساعت ۱۰ خرید کنم",
        "user_id": 123,
        "message_type": "text",
        "messages": [] # Start with empty message history for new conversation
    }

    # Invoke the graph
    # For streaming output, use `app.stream()`
    # For a single final state, use `app.invoke()`
    final_state = lang_graph_app.invoke(initial_input, config=config)

    logger.info(f"Graph execution finished. Final state for '{config['configurable']['thread_id']}':")
    logger.info(f"  Input: {initial_input.get('input_text')}")
    logger.info(f"  Intent: {final_state.get('current_intent')}")
    logger.info(f"  Parameters: {final_state.get('extracted_parameters')}")
    logger.info(f"  Response: {final_state.get('response_text')}")
    logger.info(f"  Message History: {final_state.get('messages')}")

    # Example of continuing the conversation
    # Note: `messages` in input will be merged by `add_messages` with existing history
    # The `thread_id` in config must be the same to load the previous state.
    follow_up_input = {
        "input_text": "متشکرم",
        "user_id": 123,
        "message_type": "text",
         # messages will be handled by the checkpointer + add_messages
    }
    final_state_follow_up = lang_graph_app.invoke(follow_up_input, config=config)
    logger.info(f"Graph execution (follow-up). Final state for '{config['configurable']['thread_id']}':")
    logger.info(f"  Input: {follow_up_input.get('input_text')}")
    logger.info(f"  Intent: {final_state_follow_up.get('current_intent')}")
    logger.info(f"  Response: {final_state_follow_up.get('response_text')}")
    logger.info(f"  Message History (updated): {final_state_follow_up.get('messages')}")

    # This was moved to the top of the __main__ block
    # import os
    # os.makedirs("./checkpoints", exist_ok=True) 