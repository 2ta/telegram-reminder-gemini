import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
import datetime as dt # Import for datetime objects
import pytz

from langgraph.graph.message import HumanMessage, AIMessage

from src.graph_state import AgentState
from src.graph import create_graph # Import the factory function
# Import settings to allow modification for testing GEMINI_API_KEY
from config import config as app_config
from src.database import User, Reminder # For mocking DB interactions


# Since the graph uses SqliteSaver, we need to ensure the checkpoints directory exists.
import os
if not os.path.exists("./checkpoints"):
    os.makedirs("./checkpoints")

# --- Mocks for Gemini ---
@pytest.fixture
def mock_gemini_model_instance():
    """Mocks the Gemini GenerativeModel instance."""
    mock_model = MagicMock()
    # model.generate_content_async should be an AsyncMock
    mock_model.generate_content_async = AsyncMock() 
    return mock_model

@pytest.fixture(autouse=True) # Autouse to apply to all tests in this module
def mock_gemini_client(mock_gemini_model_instance):
    """Mocks genai.configure and genai.GenerativeModel."""
    with patch('google.generativeai.configure') as mock_configure, \
         patch('google.generativeai.GenerativeModel', return_value=mock_gemini_model_instance) as mock_generative_model:
        yield mock_configure, mock_generative_model, mock_gemini_model_instance

# --- Mock for datetime_utils ---
@pytest.fixture(autouse=True)
def mock_datetime_parser():
    # This mock will apply to all tests in this file.
    # Individual tests can override its return_value if needed.
    with patch('src.graph_nodes.parse_persian_datetime_to_utc') as mock_parser:
        # Default behavior: successfully parse to a fixed UTC datetime
        mock_parser.return_value = dt.datetime(2024, 1, 1, 10, 30, 0, tzinfo=pytz.utc) # Use pytz.utc
        yield mock_parser

# --- Mock for Database ---
@pytest.fixture
def mock_db_session():
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = MagicMock(spec=User) # Default: user exists
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.close = MagicMock()
    return mock_session

@pytest.fixture(autouse=True) # Apply to all tests that might use the DB
def mock_get_db(mock_db_session):
    with patch('src.graph_nodes.get_db', return_value=iter([mock_db_session])) as mock_get:
        yield mock_get


# --- Test Graph App Fixture ---
@pytest.fixture(scope="module")
def test_graph_app_module_scoped():
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_test_key"

    with patch('langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string') as mock_sqlite_saver:
        mock_checkpointer_instance = MagicMock()
        # Ensure .get() and .put() are awaitable if the checkpointer expects async methods
        mock_checkpointer_instance.get = AsyncMock(return_value=None) 
        mock_checkpointer_instance.put = AsyncMock(return_value=None)
        mock_sqlite_saver.return_value = mock_checkpointer_instance
        graph_app = create_graph()

    app_config.settings.GEMINI_API_KEY = original_api_key
    return graph_app, mock_checkpointer_instance


@pytest.mark.asyncio
async def test_graph_compilation_and_structure(test_graph_app_module_scoped):
    graph_app, _ = test_graph_app_module_scoped
    assert graph_app is not None
    assert graph_app.nodes is not None
    # Check for presence of key nodes
    assert "entry_node" in graph_app.nodes
    assert "determine_intent_node" in graph_app.nodes
    assert "process_datetime_node" in graph_app.nodes
    assert "validate_reminder_parameters_node" in graph_app.nodes # New
    assert "create_reminder_node" in graph_app.nodes          # New
    assert "handle_intent_node" in graph_app.nodes
    assert "format_response_node" in graph_app.nodes
    # Check entry point
    # Note: Accessing internal attributes like `entry_point` might be brittle.
    # Prefer testing behavior over implementation details if public API allows.
    # For now, this is a basic structural check.

@pytest.mark.asyncio
async def test_graph_greeting_intent_skips_datetime_processing(test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_test_key_for_greeting"

    user_id_str = "test_user_greeting_skip_dt"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "سلام"
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 123, "message_type": "text",
        "messages": [HumanMessage(content=input_text)],
        "parsed_datetime_utc": None # Ensure it starts as None
    }
    mock_checkpointer.get.return_value = None # Simulate no previous state

    # Mock Gemini response for greeting
    gemini_response_payload = {"intent": "greeting", "parameters": {}}
    mock_response_obj = MagicMock()
    mock_response_obj.text = json.dumps(gemini_response_payload)
    mock_model_instance.generate_content_async.return_value = mock_response_obj

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)

    assert final_state["current_intent"] == "greeting"
    assert "سلام! چطور می‌توانم کمکتان کنم؟" in final_state["response_text"]
    mock_datetime_parser.assert_not_called() # Datetime parsing should be skipped
    assert final_state.get("parsed_datetime_utc") is None # Should remain None
    mock_model_instance.generate_content_async.assert_awaited_once()
    mock_checkpointer.put.assert_called_once()
    # ... (assertions for saved state can be added here too)

    app_config.settings.GEMINI_API_KEY = original_api_key # Restore


@pytest.mark.asyncio
async def test_graph_create_reminder_with_datetime_processing(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_for_reminder_dt"

    user_id_str = "test_user_reminder_dt"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "یادآوری کن فردا ساعت ۱۰ صبح جلسه دارم"
    raw_date_param = "فردا"
    raw_time_param = "ساعت ۱۰ صبح"
    
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 456, "message_type": "text",
        "messages": [HumanMessage(content=input_text)],
        "parsed_datetime_utc": None
    }

    gemini_response_payload = {
        "intent": "create_reminder",
        "parameters": {"task": "جلسه دارم", "date": raw_date_param, "time": raw_time_param}
    }
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response_payload)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    # Configure the mock datetime parser for this specific test
    # MOCK_NOW_JALALI = jdatetime.datetime(1403, 4, 30, 10, 0, 0) # 30 Tir 1403, 10:00 AM
    # "فردا ساعت ۱۰ صبح" (July 22, 2024, 10:00 AM Tehran time if "now" is July 21 10:00 AM Tehran)
    # If mock "now" is 1403/4/30 10:00 (2024-07-20 10:00 Tehran), "فردا" is 1403/5/1 (2024-07-22)
    # "ساعت ۱۰ صبح" -> 10:00. So, 1403/5/1 10:00 Tehran.
    # This is 2024-07-22 10:00:00+03:30 -> 2024-07-22 06:30:00 UTC
    expected_parsed_dt = dt.datetime(2024, 7, 22, 6, 30, 0, tzinfo=dt.timezone.utc)
    mock_datetime_parser.return_value = expected_parsed_dt

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["extracted_parameters"]["task"] == "جلسه دارم"
    mock_datetime_parser.assert_called_once_with(raw_date_param, raw_time_param)
    assert final_state["parsed_datetime_utc"] == expected_parsed_dt
    
    # Check response text formatting (assuming Tehran is UTC+3:30 for display via jdatetime)
    # expected_parsed_dt (UTC) -> Tehran time: 2024-07-22 10:00:00+03:30
    # jdatetime.fromgregorian(datetime=datetime(2024,7,22,10,0,0)).strftime("%Y/%m/%d ساعت %H:%M")
    # -> "۱۴۰۳/۰۵/۰۱ ساعت ۱۰:۰۰"
    expected_display_datetime = "۱۴۰۳/۰۵/۰۱ ساعت ۱۰:۰۰"
    assert f"'{expected_display_datetime}' (به وقت تهران) تنظیم می‌شود" in final_state["response_text"]
    
    mock_model_instance.generate_content_async.assert_awaited_once()
    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_create_reminder_datetime_parsing_fails(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_for_reminder_dt_fail"

    user_id_str = "test_user_reminder_dt_fail"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "یادآوری کن فردا یه کاری دارم"
    raw_date_param = "فردای نامعلوم" # Invalid date to make parsing fail
    raw_time_param = None
    
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 457, "message_type": "text",
        "messages": [HumanMessage(content=input_text)],
        "parsed_datetime_utc": "initial_dummy_value" # Make sure it gets overwritten to None
    }

    gemini_response_payload = {
        "intent": "create_reminder",
        "parameters": {"task": "یه کاری دارم", "date": raw_date_param, "time": raw_time_param}
    }
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response_payload)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    mock_datetime_parser.return_value = None # Simulate parsing failure

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)

    assert final_state["current_intent"] == "create_reminder"
    mock_datetime_parser.assert_called_once_with(raw_date_param, raw_time_param)
    assert final_state["parsed_datetime_utc"] is None
    assert "قابل فهم نبود. لطفا دقیق‌تر بگویید." in final_state["response_text"]
    
    app_config.settings.GEMINI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_graph_gemini_api_key_not_set(test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client 
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = None

    user_id_str = "test_user_no_api_key_dt" # Make user_id unique
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "هر پیامی"
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 789, "message_type": "text",
        "messages": [HumanMessage(content=input_text)]
    }

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)

    assert final_state["current_intent"] == "unknown_intent"
    assert f"متاسفانه منظور شما از '{input_text}' را متوجه نشدم." in final_state["response_text"]
    mock_model_instance.generate_content_async.assert_not_called()
    mock_datetime_parser.assert_not_called() # Should also not be called if intent is unknown early

    app_config.settings.GEMINI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_graph_gemini_api_error(test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_for_api_error_dt"

    user_id_str = "test_user_api_error_dt"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "تست با خطای ای پی آی"
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 101, "message_type": "text",
        "messages": [HumanMessage(content=input_text)]
    }
    
    mock_model_instance.generate_content_async.side_effect = Exception("Simulated Gemini API Error")

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)

    assert final_state["current_intent"] == "unknown_intent"
    assert "خطایی در پردازش درخواست شما با Gemini رخ داد." in final_state["response_text"]
    mock_datetime_parser.assert_not_called() # Datetime processing shouldn't happen
    app_config.settings.GEMINI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_graph_gemini_malformed_json_response(test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_for_json_error_dt"

    user_id_str = "test_user_json_error_dt"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "تست با جیسون خراب"
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 112, "message_type": "text",
        "messages": [HumanMessage(content=input_text)]
    }

    mock_response_obj = MagicMock()
    mock_response_obj.text = "This is not JSON { intent: 'bla' " 
    mock_model_instance.generate_content_async.return_value = mock_response_obj

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)
    
    assert final_state["current_intent"] == "unknown_intent"
    assert "خطایی در پردازش درخواست شما با Gemini رخ داد." in final_state["response_text"]
    mock_datetime_parser.assert_not_called()
    app_config.settings.GEMINI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_graph_gemini_empty_response_text(test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_for_empty_response_dt"

    user_id_str = "test_user_empty_response_dt"
    config = {"configurable": {"thread_id": user_id_str}}
    input_text = "تست با پاسخ خالی"
    initial_state: AgentState = {
        "input_text": input_text, "user_id": 113, "message_type": "text",
        "messages": [HumanMessage(content=input_text)]
    }
    
    mock_response_obj = MagicMock()
    mock_response_obj.text = "" 
    mock_model_instance.generate_content_async.return_value = mock_response_obj

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state, config=config)
    
    assert final_state["current_intent"] == "unknown_intent"
    assert f"متاسفانه منظور شما از '{input_text}' را متوجه نشدم." in final_state["response_text"]
    mock_datetime_parser.assert_not_called()
    app_config.settings.GEMINI_API_KEY = original_api_key

# The old test_graph_unknown_intent_invocation is now covered by various Gemini error/fallback cases.
# If specific non-Gemini unknown intent handling is still desired, it could be adapted,
# but typically Gemini would classify truly unknown things as "unknown_intent" based on the prompt.

# Remove or adapt old tests that don't use Gemini mocks if they are redundant
# For example, test_graph_simple_invocation_greeting and test_graph_reminder_intent_invocation
# are now superseded by their _with_gemini versions. 

# --- Test Cases for Reminder Creation Flow ---

@pytest.mark.asyncio
async def test_graph_create_reminder_successful(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_success"

    user_id_val = 111
    chat_id_val = 111
    user_id_str = f"test_user_reminder_success_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    input_text = "یادآوری کن فردا ساعت ۱۱ برای جلسه"
    task_desc = "برای جلسه"
    raw_date = "فردا"
    raw_time = "ساعت ۱۱"

    initial_state_dict: AgentState = {
        "input_text": input_text, "user_id": user_id_val, "chat_id": chat_id_val, "message_type": "text",
        "messages": [HumanMessage(content=input_text)],
        "parsed_datetime_utc": None, "validated_task": None, "reminder_creation_status": None
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": raw_date, "time": raw_time}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    # Specific datetime for this test
    # "فردا ساعت ۱۱" (if now is 2024-01-01 10:30 UTC, then tomorrow is 2024-01-02)
    # 11:00 Tehran time. Tehran is UTC+3:30. So 11:00 Tehran = 07:30 UTC.
    # Using the default mock_datetime_parser time for simplicity in this example calculation, not dynamic from mock_now.
    # Let's assume parsed_datetime_utc.get_current_tehran_times() is mocked or test assumes a fixed "now" for datetime_utils.
    # For the purpose of THIS test, we just need a consistent datetime.
    # The mock_datetime_parser returns 2024-01-01 10:30:00 UTC by default.
    # Let's make it something that would be "فردا ساعت ۱۱" relative to a hypothetical now.
    # For 1402/10/12 11:00 Tehran time (which is 2024-01-02 11:00 Tehran if 1402/10/11 was 2024-01-01)
    # = 2024-01-02 07:30:00 UTC
    parsed_dt = dt.datetime(2024, 1, 2, 7, 30, 0, tzinfo=pytz.utc)
    mock_datetime_parser.return_value = parsed_dt

    # Mock DB user found
    mock_user_instance = MagicMock(spec=User)
    mock_user_instance.id = 1 # internal DB id
    mock_user_instance.user_id = user_id_val # telegram id
    mock_user_instance.chat_id = chat_id_val
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user_instance
    
    # Mock DB reminder creation success
    mock_db_session.commit = MagicMock() # Ensure it can be called without error

    # Capture what's passed to db.add
    added_object = None
    def capture_add(obj):
        nonlocal added_object
        added_object = obj
    mock_db_session.add = MagicMock(side_effect=capture_add)

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["extracted_parameters"]["task"] == task_desc
    mock_datetime_parser.assert_called_once_with(raw_date, raw_time)
    assert final_state["parsed_datetime_utc"] == parsed_dt
    assert final_state["validated_task"] == task_desc
    assert final_state["reminder_creation_status"] == "success"
    
    # Check successful response message. (parsed_dt to Jalali "۱۴۰۲/۱۰/۱۲ ساعت ۱۱:۰۰")
    # jdatetime.datetime.fromgregorian(datetime=parsed_dt.astimezone(pytz.timezone('Asia/Tehran')))
    # gives 1402-10-12 11:00:00+03:30. strftime -> ۱۴۰۲/۱۰/۱۲ ساعت ۱۱:۰۰
    assert "یادآور شما برای «برای جلسه» در تاریخ و ساعت «۱۴۰۲/۱۰/۱۲ ساعت ۱۱:۰۰» (به وقت تهران) با موفقیت ایجاد شد." in final_state["response_text"]

    mock_model_instance.generate_content_async.assert_awaited_once()
    mock_db_session.add.assert_called_once() # Check if Reminder object was added
    assert added_object is not None
    assert isinstance(added_object, Reminder)
    assert added_object.user_db_id == mock_user_instance.id # Check FK
    assert added_object.telegram_user_id == user_id_val      # Check Telegram ID
    assert added_object.task_description == task_desc
    assert added_object.due_datetime_utc == parsed_dt
    mock_db_session.commit.assert_called_once()

    app_config.settings.GEMINI_API_KEY = original_api_key


@pytest.mark.asyncio
async def test_graph_create_reminder_missing_task(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_no_task"

    user_id_val = 222
    user_id_str = f"test_user_reminder_no_task_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    initial_state_dict: AgentState = {
        "input_text": "یادآوری کن فردا", "user_id": user_id_val, "chat_id": user_id_val, "message_type": "text",
        "messages": [HumanMessage(content="یادآوری کن فردا")],
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"date": "فردا", "time": None, "task": ""}} # Empty task
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["reminder_creation_status"] == "error_missing_task"
    assert "لطفاً مشخص کنید برای چه کاری می‌خواهید یادآور تنظیم کنید." in final_state["response_text"]
    mock_datetime_parser.assert_called_once_with("فردا", None) # Datetime parsing might still happen before validation logic
    
    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_create_reminder_datetime_parse_fails_in_validation(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_dt_fail_validation"

    user_id_val = 333
    user_id_str = f"test_user_reminder_dt_fail_val_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    task_desc = "یه کاری"
    raw_date_invalid = "تاریخ نامعتبر"
    initial_state_dict: AgentState = {
        "input_text": f"یادآوری کن {raw_date_invalid} {task_desc}", 
        "user_id": user_id_val, "chat_id": user_id_val, "message_type": "text",
        "messages": [HumanMessage(content=f"یادآوری کن {raw_date_invalid} {task_desc}")],
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": raw_date_invalid, "time": None}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    mock_datetime_parser.return_value = None # Simulate datetime parsing failure

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)
    
    assert final_state["current_intent"] == "create_reminder"
    assert final_state["parsed_datetime_utc"] is None
    assert final_state["reminder_creation_status"] == "error_missing_datetime"
    assert f"برای «{task_desc}» چه تاریخ و ساعتی مدنظرتان است؟ زمان ارائه شده قابل فهم نبود." in final_state["response_text"]
    mock_datetime_parser.assert_called_once_with(raw_date_invalid, None)
    
    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_create_reminder_db_error(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_db_error"

    user_id_val = 444
    user_id_str = f"test_user_reminder_db_error_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    task_desc = "تست خطای دیتابیس"
    initial_state_dict: AgentState = {
        "input_text": f"یادآوری کن فردا {task_desc}", "user_id": user_id_val, "chat_id": user_id_val, "message_type": "text",
        "messages": [HumanMessage(content=f"یادآوری کن فردا {task_desc}")],
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": "فردا", "time": "صبح"}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj
    
    # Datetime parsing succeeds
    mock_datetime_parser.return_value = dt.datetime(2024, 1, 2, 5, 30, 0, tzinfo=pytz.utc) # صبح فردا -> 9:00 Tehran -> 05:30 UTC

    # Mock DB user found
    mock_user_instance = MagicMock(spec=User)
    mock_user_instance.id = 2 # internal DB id
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user_instance
    
    # Mock DB commit error
    mock_db_session.commit = MagicMock(side_effect=Exception("Simulated DB commit error"))

    # Capture what's passed to db.add to check its attributes
    added_object_on_error = None
    def capture_add_on_error(obj):
        nonlocal added_object_on_error
        added_object_on_error = obj
    mock_db_session.add = MagicMock(side_effect=capture_add_on_error)

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["reminder_creation_status"] == "db_error"
    assert "متاسفانه در حال حاضر مشکلی در ذخیره یادآور شما پیش آمده." in final_state["response_text"]
    
    mock_db_session.add.assert_called_once() # Add would still be called
    assert added_object_on_error is not None
    assert isinstance(added_object_on_error, Reminder)
    assert added_object_on_error.user_db_id == mock_user_instance.id
    assert added_object_on_error.telegram_user_id == user_id_val

    mock_db_session.commit.assert_called_once() # Commit was attempted
    mock_db_session.rollback.assert_called_once() # Rollback should be called on error

    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_create_reminder_user_created_during_flow(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_new_user"

    user_id_val = 555 # New user telegram ID
    chat_id_val = 555
    user_id_str = f"test_user_reminder_new_user_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    task_desc = "خرید برای کاربر جدید"
    initial_state_dict: AgentState = {
        "input_text": f"یادآوری کن فردا صبح {task_desc}", 
        "user_id": user_id_val, 
        "chat_id": chat_id_val, 
        "message_type": "text",
        "messages": [HumanMessage(content=f"یادآوری کن فردا صبح {task_desc}")],
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": "فردا", "time": "صبح"}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    mock_datetime_parser.return_value = dt.datetime(2024, 1, 2, 5, 30, 0, tzinfo=pytz.utc)

    # Mock DB: User not found initially, then successfully created and reminder added
    created_user_instance = MagicMock(spec=User, id=3, user_id=user_id_val, chat_id=chat_id_val)
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [
        None, # First call for User.user_id returns None (user not found)
        created_user_instance # Subsequent calls might occur (e.g. if user is re-queried, though not in current code)
    ]
    
    added_objects = []
    original_add = mock_db_session.add
    def side_effect_add(obj):
        nonlocal added_objects
        added_objects.append(obj)
        # Simulate that db.refresh(user) would add attributes like id to the user object passed to add
        if isinstance(obj, User) and not hasattr(obj, 'id'):
            obj.id = created_user_instance.id # Simulate refresh setting the ID
        return original_add(obj)
    mock_db_session.add = MagicMock(side_effect=side_effect_add)
    mock_db_session.commit = MagicMock() # Reset commit mock for this test

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["reminder_creation_status"] == "success"
    assert "یادآور شما برای «خرید برای کاربر جدید»" in final_state["response_text"]

    # Check that query for user was called (at least once to find it missing)
    assert mock_db_session.query.return_value.filter.return_value.first.call_count >= 1
    # Check that add was called for User and Reminder
    user_added_to_session.assert_called_once() 
    reminder_added_to_session.assert_called_once()
    assert mock_db_session.commit.call_count == 2 # One for User, one for Reminder

    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_create_reminder_limit_exceeded_free_tier(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_limit_free"
    original_free_limit = app_config.settings.MAX_REMINDERS_FREE_TIER
    app_config.settings.MAX_REMINDERS_FREE_TIER = 1 # Set a low limit for test

    user_id_val = 666
    chat_id_val = 666
    user_id_str = f"test_user_reminder_limit_free_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    task_desc = "Exceed limit task"
    initial_state_dict: AgentState = {
        "input_text": f"یادآوری کن فردا {task_desc}", 
        "user_id": user_id_val, "chat_id": chat_id_val, "message_type": "text",
        "messages": [HumanMessage(content=f"یادآوری کن فردا {task_desc}")],
        "parsed_datetime_utc": None, "validated_task": None, "reminder_creation_status": None
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": "فردا", "time": "صبح"}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj
    mock_datetime_parser.return_value = dt.datetime(2024, 1, 2, 5, 30, 0, tzinfo=pytz.utc)

    # Mock DB: User exists, is_premium=False
    mock_user_instance = MagicMock(spec=User, id=4, user_id=user_id_val, chat_id=chat_id_val, is_premium=False)
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user_instance
    
    # Mock DB: Reminder count is at the limit (1)
    mock_db_session.query.return_value.filter.return_value.scalar.return_value = 1

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["reminder_creation_status"] == "error_limit_exceeded"
    assert "شما به حداکثر تعداد یادآورهای فعال خود رسیده‌اید." in final_state["response_text"]
    
    mock_db_session.add.assert_not_called() # Reminder should not be added
    mock_db_session.commit.assert_not_called() # Commit should not happen for reminder

    app_config.settings.GEMINI_API_KEY = original_api_key
    app_config.settings.MAX_REMINDERS_FREE_TIER = original_free_limit # Restore limit

@pytest.mark.asyncio
async def test_graph_create_reminder_below_limit_free_tier(
    test_graph_app_module_scoped, mock_gemini_client, mock_datetime_parser, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_reminder_ok_free"
    original_free_limit = app_config.settings.MAX_REMINDERS_FREE_TIER
    app_config.settings.MAX_REMINDERS_FREE_TIER = 5

    user_id_val = 777
    chat_id_val = 777
    user_id_str = f"test_user_reminder_ok_free_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    task_desc = "Within limit task"
    initial_state_dict: AgentState = {
        "input_text": f"یادآوری کن پس فردا {task_desc}", 
        "user_id": user_id_val, "chat_id": chat_id_val, "message_type": "text",
        "messages": [HumanMessage(content=f"یادآوری کن پس فردا {task_desc}")],
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "create_reminder", "parameters": {"task": task_desc, "date": "پس فردا", "time": "عصر"}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj
    parsed_dt = dt.datetime(2024, 1, 3, 13, 30, 0, tzinfo=pytz.utc) # پس فردا عصر -> 17:00 Tehran -> 13:30 UTC
    mock_datetime_parser.return_value = parsed_dt

    # Mock DB: User exists, is_premium=False
    mock_user_instance = MagicMock(spec=User, id=5, user_id=user_id_val, chat_id=chat_id_val, is_premium=False)
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user_instance
    
    # Mock DB: Reminder count is below limit (e.g., 0)
    # We need to ensure the query for count is separate from the query for user
    # The .scalar() should be on the count query.
    mock_user_query = mock_db_session.query.return_value.filter.return_value
    mock_user_query.first.return_value = mock_user_instance

    mock_count_query = MagicMock()
    mock_count_query.scalar.return_value = 0 # User has 0 active reminders
    mock_db_session.query.return_value.filter.return_value = mock_count_query # for the count query

    # Reset add and commit mocks for this test
    mock_db_session.add = MagicMock()
    mock_db_session.commit = MagicMock()

    loop = asyncio.get_event_loop()
    # We need to make sure the db session mock is versatile enough for two types of queries.
    # One for user, one for count. The current mock_db_session might be too simple.
    # For now, let's assume the structure of create_reminder_node first queries user, then count.
    # Side effect for query.filter.first (for user) and query.filter.scalar (for count)
    mock_db_session.query.side_effect = [
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_user_instance)))), # For User query
        MagicMock(filter=MagicMock(return_value=MagicMock(scalar=MagicMock(return_value=0)))) # For Reminder count query
    ]

    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "create_reminder"
    assert final_state["reminder_creation_status"] == "success"
    assert "با موفقیت ایجاد شد." in final_state["response_text"]
    
    mock_db_session.add.assert_called_once()
    # Commit for user creation (if any) and reminder creation
    # If user exists, only 1 commit for reminder. If user created, 2 commits.
    # Here user exists so 1 commit for reminder.
    assert mock_db_session.commit.call_count >= 1 

    app_config.settings.GEMINI_API_KEY = original_api_key
    app_config.settings.MAX_REMINDERS_FREE_TIER = original_free_limit # Restore limit

# Similar tests for PREMIUM_TIER can be added: test_graph_create_reminder_limit_exceeded_premium_tier
# and test_graph_create_reminder_below_limit_premium_tier

# --- Test Cases for View Reminders Flow ---

@pytest.mark.asyncio
async def test_graph_view_reminders_no_reminders(
    test_graph_app_module_scoped, mock_gemini_client, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_view_reminders_empty"

    user_id_val = 888
    chat_id_val = 888
    user_id_str = f"test_user_view_reminders_empty_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    initial_state_dict: AgentState = {
        "input_text": "یادآورهامو ببینم", "user_id": user_id_val, "chat_id": chat_id_val, "message_type": "text",
        "messages": [HumanMessage(content="یادآورهامو ببینم")]
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "view_reminders", "parameters": {}} # No specific filters
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    # Mock DB: User exists
    mock_user_instance = MagicMock(spec=User, id=6, user_id=user_id_val, chat_id=chat_id_val, is_premium=False)
    # Mock DB: No active reminders for this user
    mock_db_session.query.side_effect = [
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_user_instance)))), # For User query
        MagicMock(filter=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))) # For Reminder query -> empty list
    ]

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "view_reminders"
    assert "شما در حال حاضر هیچ یادآور فعالی ندارید." in final_state["response_text"]
    mock_model_instance.generate_content_async.assert_awaited_once()
    # Check that user query was made, then reminder query was made
    assert mock_db_session.query.call_count == 2

    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_view_reminders_with_active_reminders(
    test_graph_app_module_scoped, mock_gemini_client, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_view_reminders_active"

    user_id_val = 999
    chat_id_val = 999
    user_db_id = 7
    user_id_str = f"test_user_view_reminders_active_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    initial_state_dict: AgentState = {
        "input_text": "یادآوری های من", "user_id": user_id_val, "chat_id": chat_id_val, "message_type": "text",
        "messages": [HumanMessage(content="یادآوری های من")]
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "view_reminders", "parameters": {}} # No specific filters
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    # Mock DB: User exists
    mock_user_instance = MagicMock(spec=User, id=user_db_id, user_id=user_id_val, chat_id=chat_id_val, is_premium=True)
    
    # Mock DB: Active reminders for this user
    # Reminder 1: 2024-01-05 10:00:00 UTC (1402/10/15 13:30 Tehran)
    # Reminder 2: 2024-01-06 12:30:00 UTC (1402/10/16 16:00 Tehran)
    mock_reminders = [
        MagicMock(spec=Reminder, id=1, user_db_id=user_db_id, task_description="جلسه اول", due_datetime_utc=dt.datetime(2024, 1, 5, 10, 0, 0, tzinfo=pytz.utc), is_active=True),
        MagicMock(spec=Reminder, id=2, user_db_id=user_db_id, task_description="ددلاین پروژه", due_datetime_utc=dt.datetime(2024, 1, 6, 12, 30, 0, tzinfo=pytz.utc), is_active=True)
    ]
    mock_db_session.query.side_effect = [
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_user_instance)))), # For User query
        MagicMock(filter=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_reminders)))))) # For Reminder query
    ]

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "view_reminders"
    response_text = final_state["response_text"]
    assert "یادآورهای فعال شما:" in response_text
    assert "- «جلسه اول» در ۱۴۰۲/۱۰/۱۵ ساعت ۱۳:۳۰" in response_text
    assert "- «ددلاین پروژه» در ۱۴۰۲/۱۰/۱۶ ساعت ۱۶:۰۰" in response_text
    
    mock_model_instance.generate_content_async.assert_awaited_once()
    assert mock_db_session.query.call_count == 2

    app_config.settings.GEMINI_API_KEY = original_api_key

@pytest.mark.asyncio
async def test_graph_view_reminders_user_not_found(
    test_graph_app_module_scoped, mock_gemini_client, mock_db_session
):
    graph_app, mock_checkpointer = test_graph_app_module_scoped
    _, _, mock_model_instance = mock_gemini_client
    original_api_key = app_config.settings.GEMINI_API_KEY
    app_config.settings.GEMINI_API_KEY = "fake_key_view_reminders_no_user"

    user_id_val = 1001 # Non-existent user
    user_id_str = f"test_user_view_reminders_no_user_{user_id_val}"
    config_thread = {"configurable": {"thread_id": user_id_str}}
    initial_state_dict: AgentState = {
        "input_text": "ببینم چه خبره", "user_id": user_id_val, "chat_id": 1001, "message_type": "text",
        "messages": [HumanMessage(content="ببینم چه خبره")]
    }
    mock_checkpointer.get.return_value = None

    gemini_response = {"intent": "view_reminders", "parameters": {}}
    mock_gemini_response_obj = MagicMock()
    mock_gemini_response_obj.text = json.dumps(gemini_response)
    mock_model_instance.generate_content_async.return_value = mock_gemini_response_obj

    # Mock DB: User not found
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    loop = asyncio.get_event_loop()
    final_state = await loop.run_in_executor(None, graph_app.invoke, initial_state_dict, config=config_thread)

    assert final_state["current_intent"] == "view_reminders"
    assert "شما هنوز هیچ یادآوری ثبت نکرده‌اید یا حساب کاربری شما یافت نشد." in final_state["response_text"]
    mock_model_instance.generate_content_async.assert_awaited_once()
    # Only one query for user, which returns None, so reminder query shouldn't happen
    mock_db_session.query.return_value.filter.return_value.first.assert_called_once()

    app_config.settings.GEMINI_API_KEY = original_api_key

# ... (rest of the file) ... 