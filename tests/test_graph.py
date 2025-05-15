import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from langgraph.graph.message import HumanMessage, AIMessage

from src.graph_state import AgentState
from src.graph import create_graph # Import the factory function
# Import specific intents for assertion comparison
from resources.prompts import INTENT_DETECTION_SYSTEM_PROMPT # To get intent names like CREATE_REMINDER, GREETING etc.

# It's better to extract actual intent names if they are defined as constants in prompts.py
# For now, let's assume we know them or can define them here for tests.
CREATE_REMINDER_INTENT = "CREATE_REMINDER"
GREETING_INTENT = "GREETING"
UNKNOWN_INTENT = "UNKNOWN"
HELP_INTENT = "HELP"


# Since the graph uses SqliteSaver, we need to ensure the checkpoints directory exists.
import os
if not os.path.exists("./checkpoints"):
    os.makedirs("./checkpoints")

@pytest.fixture(scope="module")
def test_graph_app_nlu(): # Renamed fixture for clarity
    # Patch the LLM utility function used by graph nodes
    with patch('src.graph_nodes.get_llm_json_response', new_callable=AsyncMock) as mock_llm_call, \
         patch('langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string') as mock_sqlite_saver:
        
        mock_checkpointer_instance = MagicMock()
        # Simulate the checkpointer's get_tuple method if LangGraph calls it
        mock_checkpoint_tuple = MagicMock()
        mock_checkpoint_tuple.config = {}
        mock_checkpoint_tuple.checkpoint = {}
        mock_checkpoint_tuple.parent_config = {}

        # If .get() returns None or raises an exception for new threads, that's fine.
        # If it returns a tuple for existing threads, mock that.
        mock_checkpointer_instance.get = MagicMock(return_value=None) 
        mock_checkpointer_instance.get_tuple = MagicMock(return_value=mock_checkpoint_tuple) # For subsequent calls for same thread_id
        
        # Mock 'put' to do nothing or minimal validation if needed
        mock_checkpointer_instance.put = MagicMock()

        mock_sqlite_saver.return_value = mock_checkpointer_instance
        
        graph_app = create_graph()
        yield graph_app, mock_llm_call, mock_checkpointer_instance # Yield all mocks needed by tests

@pytest.mark.asyncio
async def test_graph_nlu_structure_and_nodes(test_graph_app_nlu):
    graph_app, _, _ = test_graph_app_nlu
    assert graph_app is not None
    assert "determine_intent_node" in graph_app.nodes
    assert "extract_parameters_node" in graph_app.nodes # New node
    assert "handle_intent_node" in graph_app.nodes

@pytest.mark.asyncio
async def test_graph_nlu_greeting_flow(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    
    user_id_str = "test_user_nlu_greeting"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "سلام وقت بخیر"
    
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 777,
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    # Simulate LLM response for intent detection
    mock_llm_call.side_effect = [
        {"intent": GREETING_INTENT} # First call for determine_intent_node
        # No second call expected as it won't go to extract_parameters_node
    ]
    mock_checkpointer.get.return_value = None # Simulate new conversation

    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == GREETING_INTENT
    assert "سلام! چطور می‌توانم کمکتان کنم؟" in final_state["response_text"]
    # Check that LLM was called once for intent detection
    assert mock_llm_call.call_count == 1
    # Verify args of the first call (intent detection)
    intent_call_args = mock_llm_call.call_args_list[0]
    assert intent_call_args[1]['input_variables']['user_input'] == initial_input_text
    
    # Check messages in saved state
    mock_checkpointer.put.assert_called_once()
    saved_config, saved_state_checkpoint = mock_checkpointer.put.call_args[0]
    # LangGraph SqliteSaver saves a tuple: (checkpoint, config, parent_config)
    # The 'checkpoint' is what we need to inspect from the tuple
    # We need to look at the actual state passed to `put`, which is the second argument, the checkpoint itself.
    
    # SqliteSaver.put(self, config: RunnableConfig, checkpoint: Checkpoint, parent_config: Optional[RunnableConfig])
    # So, saved_state is checkpoint['channel_values']['messages'] if using default `update_checkpoint`
    # Or more generally, the 'messages' key from the checkpoint's AgentState content.

    # The object passed to `put` is a Checkpoint dict.
    # Let's assume AgentState is directly under a known key or is the checkpoint itself.
    # If SqliteSaver wraps it, the structure might be different.
    # For now, let's assume the 'checkpoint' dict contains our AgentState fields.
    saved_state_content = saved_state_checkpoint # This 'checkpoint' is the dict from langgraph
    
    assert any(isinstance(m, HumanMessage) and m.content == initial_input_text for m in saved_state_content['messages'])
    assert any(isinstance(m, AIMessage) and "سلام! چطور می‌توانم کمکتان کنم؟" in m.content for m in saved_state_content['messages'])


@pytest.mark.asyncio
async def test_graph_nlu_create_reminder_flow(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    
    user_id_str = "test_user_nlu_reminder"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "یادآوری کن فردا ساعت ۱۰ صبح خرید کنم"
    
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 888,
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    # Simulate LLM responses
    mock_llm_call.side_effect = [
        {"intent": CREATE_REMINDER_INTENT}, # For determine_intent_node
        {"task": "خرید کنم", "date": "فردا", "time": "۱۰ صبح"} # For extract_parameters_node
    ]
    mock_checkpointer.get.return_value = None # Simulate new conversation


    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == CREATE_REMINDER_INTENT
    assert final_state["extracted_parameters"]["task"] == "خرید کنم"
    assert final_state["extracted_parameters"]["date_str"] == "فردا"
    assert final_state["extracted_parameters"]["time_str"] == "۱۰ صبح"
    assert "قصد شما برای ایجاد یادآور دریافت شد" in final_state["response_text"]
    assert "وظیفه='خرید کنم'" in final_state["response_text"]
    assert "تاریخ='فردا'" in final_state["response_text"]
    assert "زمان='۱۰ صبح'" in final_state["response_text"]
    
    assert mock_llm_call.call_count == 2
    # Check intent detection call
    intent_call_args = mock_llm_call.call_args_list[0]
    assert intent_call_args[1]['input_variables']['user_input'] == initial_input_text
    # Check parameter extraction call
    param_call_args = mock_llm_call.call_args_list[1]
    assert param_call_args[1]['input_variables']['user_input'] == initial_input_text

    mock_checkpointer.put.assert_called_once()
    # Further assertions on saved state can be added here similar to the greeting test

@pytest.mark.asyncio
async def test_graph_nlu_unknown_intent_flow(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    user_id_str = "test_user_nlu_unknown"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "آب و هوا چطوره؟"
    initial_state: AgentState = {
        "input_text": initial_input_text,
        "user_id": 999,
        "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    mock_llm_call.side_effect = [
        {"intent": UNKNOWN_INTENT} 
    ]
    mock_checkpointer.get.return_value = None

    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == UNKNOWN_INTENT
    assert "متوجه منظور شما نشدم" in final_state["response_text"]
    assert mock_llm_call.call_count == 1
    mock_checkpointer.put.assert_called_once()

@pytest.mark.asyncio
async def test_graph_nlu_llm_error_in_intent_detection(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    user_id_str = "test_user_nlu_intent_error"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "تست خطا"
    initial_state: AgentState = {
        "input_text": initial_input_text, "user_id": 101, "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    mock_llm_call.side_effect = ValueError("LLM API Error") # Simulate error
    mock_checkpointer.get.return_value = None

    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == UNKNOWN_INTENT # Fallback
    assert "متوجه منظور شما نشدم" in final_state["response_text"] # Default error response
    assert mock_llm_call.call_count == 1 # Called once, then error
    mock_checkpointer.put.assert_called_once()


@pytest.mark.asyncio
async def test_graph_nlu_llm_error_in_param_extraction(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    user_id_str = "test_user_nlu_param_error"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "یادآوری خرید"
    initial_state: AgentState = {
        "input_text": initial_input_text, "user_id": 102, "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    mock_llm_call.side_effect = [
        {"intent": CREATE_REMINDER_INTENT}, # Intent success
        ValueError("LLM Param API Error")    # Param extraction error
    ]
    mock_checkpointer.get.return_value = None

    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == CREATE_REMINDER_INTENT
    # Parameters might be fallback (e.g., task=input_text, others None)
    assert final_state["extracted_parameters"]["task"] == initial_input_text 
    assert final_state["extracted_parameters"]["date_str"] is None # Based on current fallback
    assert final_state["extracted_parameters"]["time_str"] is None # Based on current fallback
    assert "قصد شما برای ایجاد یادآور دریافت شد" in final_state["response_text"] # Still acknowledges intent
    assert f"وظیفه='{initial_input_text}'" in final_state["response_text"]

    assert mock_llm_call.call_count == 2
    mock_checkpointer.put.assert_called_once()

@pytest.mark.asyncio
async def test_graph_nlu_llm_param_extraction_missing_task(test_graph_app_nlu):
    graph_app, mock_llm_call, mock_checkpointer = test_graph_app_nlu
    user_id_str = "test_user_nlu_param_no_task"
    config = {"configurable": {"thread_id": user_id_str}}
    initial_input_text = "یادآوری کن فردا" # No clear task in this part for LLM
    initial_state: AgentState = {
        "input_text": initial_input_text, "user_id": 103, "message_type": "text",
        "messages": [HumanMessage(content=initial_input_text)]
    }

    mock_llm_call.side_effect = [
        {"intent": CREATE_REMINDER_INTENT}, 
        {"date": "فردا", "time": None} # LLM returns no task
    ]
    mock_checkpointer.get.return_value = None

    final_state = await graph_app.ainvoke(initial_state, config=config)

    assert final_state["current_intent"] == CREATE_REMINDER_INTENT
    # Fallback: task should be input_text
    assert final_state["extracted_parameters"]["task"] == initial_input_text
    assert final_state["extracted_parameters"]["date_str"] == "فردا"
    assert final_state["extracted_parameters"]["time_str"] is None
    assert f"وظیفه='{initial_input_text}'" in final_state["response_text"]
    
    assert mock_llm_call.call_count == 2
    mock_checkpointer.put.assert_called_once() 