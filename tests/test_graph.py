import pytest
import asyncio
from unittest.mock import patch, MagicMock

from langgraph.graph.message import HumanMessage, AIMessage

from src.graph_state import AgentState
from src.graph import create_graph # Import the factory function

# Since the graph uses SqliteSaver, we need to ensure the checkpoints directory exists.
import os
if not os.path.exists("./checkpoints"):
    os.makedirs("./checkpoints")

# Create a graph instance for testing. This will also create the DB if it doesn't exist.
# Patch SqliteSaver to use an in-memory DB for tests to avoid file system side effects
# and ensure test isolation.
@pytest.fixture(scope="module")
def test_graph_app():
    with patch('langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string') as mock_sqlite_saver:
        # Configure the mock to return a MagicMock that simulates the checkpointer interface
        mock_checkpointer_instance = MagicMock()
        mock_sqlite_saver.return_value = mock_checkpointer_instance
        
        # When create_graph is called, it will use this mocked checkpointer
        graph_app = create_graph()
        return graph_app, mock_checkpointer_instance

@pytest.mark.asyncio
async def test_graph_compilation_and_structure(test_graph_app):
    graph_app, _ = test_graph_app
    assert graph_app is not None
    assert graph_app.nodes is not None
    # Check for presence of key nodes
    assert "entry_node" in graph_app.nodes
    assert "determine_intent_node" in graph_app.nodes
    assert "handle_intent_node" in graph_app.nodes
    assert "format_response_node" in graph_app.nodes
    # Check entry point
    # Note: Accessing internal attributes like `entry_point` might be brittle.
    # Prefer testing behavior over implementation details if public API allows.
    # For now, this is a basic structural check.

@pytest.mark.asyncio
async def test_graph_simple_invocation_greeting(test_graph_app):
    graph_app, mock_checkpointer = test_graph_app
    
    user_id = "test_user_greeting"
    config = {"configurable": {"thread_id": user_id}}
    initial_input_text = "سلام"
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 12345, # Example user_id for the state
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    # Mock the checkpointer's get method to simulate no previous state
    mock_checkpointer.get.return_value = None

    # If nodes are async, graph.invoke should handle it.
    # If graph.invoke is purely sync, run in executor for async test.
    # Based on current graph_nodes, they are async.
    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config)

    assert final_state["current_intent"] == "greeting"
    assert "سلام! چطور می‌توانم کمکتان کنم؟" in final_state["response_text"]
    assert final_state["current_node_name"] == "format_response_node" # Should end at format_response
    
    # Verify that the checkpointer's put method was called to save state
    mock_checkpointer.put.assert_called_once()
    saved_config, saved_state = mock_checkpointer.put.call_args[0]
    assert saved_config["configurable"]["thread_id"] == user_id
    # Check if AIMessage was added to messages by the graph (or if response_text handles it)
    # Based on current simple graph, messages list has HumanMessage and then AIMessage.
    # The `add_messages` updates the `messages` field in the state that is persisted.
    assert any(isinstance(m, HumanMessage) and m.content == initial_input_text for m in saved_state['messages'])
    assert any(isinstance(m, AIMessage) and "سلام! چطور می‌توانم کمکتان کنم؟" in m.content for m in saved_state['messages'])


@pytest.mark.asyncio
async def test_graph_reminder_intent_invocation(test_graph_app):
    graph_app, mock_checkpointer = test_graph_app
    user_id = "test_user_reminder"
    config = {"configurable": {"thread_id": user_id}}
    initial_input_text = "یادآوری کن جلسه ساعت ۵"
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 67890,
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }
    mock_checkpointer.get.return_value = None

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config)

    assert final_state["current_intent"] == "create_reminder_placeholder"
    assert "یادآور برای 'یادآوری کن جلسه ساعت ۵' تنظیم می‌شود" in final_state["response_text"]
    mock_checkpointer.put.assert_called_once()

@pytest.mark.asyncio
async def test_graph_unknown_intent_invocation(test_graph_app):
    graph_app, mock_checkpointer = test_graph_app
    user_id = "test_user_unknown"
    config = {"configurable": {"thread_id": user_id}}
    initial_input_text = "این یک پیام بی معنی است"
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 11223,
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }
    mock_checkpointer.get.return_value = None
    
    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config)

    assert final_state["current_intent"] == "unknown_intent"
    assert "متوجه منظور شما نشدم" in final_state["response_text"]
    mock_checkpointer.put.assert_called_once() 