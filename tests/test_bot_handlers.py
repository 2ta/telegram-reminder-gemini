import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session

from telegram import Update, User as TGUser, Message, Chat
from telegram.ext import ContextTypes # No Application needed for these tests if only mocking context.bot

from src.bot_handlers import start_command, help_command, privacy_command, get_or_create_user, text_message_handler
from src.models import User as DBUser, SubscriptionTier
# from config.config import settings # Not directly needed if language_code is always passed or default tested

@pytest.fixture
def mock_db_session():
    """Mocks the database session and user queries."""
    mock_session = MagicMock(spec=Session)
    mock_user_query = MagicMock()
    mock_session.query.return_value = mock_user_query
    mock_user_query.filter.return_value.first.return_value = None 
    return mock_session

@pytest.fixture
def mock_update_context():
    """Mocks Update and ContextTypes for handlers."""
    tg_user = TGUser(id=12345, first_name="Test", is_bot=False, last_name="User", username="testuser", language_code="en")
    chat = Chat(id=12345, type="private")
    # Make message.reply_text an AsyncMock for await
    message = Message(message_id=1, date=MagicMock(), chat=chat, from_user=tg_user, text="/start")
    message.reply_text = AsyncMock()
    
    update = Update(update_id=1, message=message)
    update.effective_user = tg_user # Ensure effective_user is set on Update
    update.effective_chat = chat # Ensure effective_chat is set for some internal PTB things
    
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    # context.bot = AsyncMock() # Not needed if we mock reply_text directly on message

    return update, context, tg_user


@pytest.mark.asyncio
@patch('src.bot_handlers.get_db')
async def test_start_command_new_user(mock_get_db, mock_db_session, mock_update_context):
    mock_get_db.return_value = iter([mock_db_session])
    update, context, tg_user_obj = mock_update_context

    mock_db_session.query(DBUser).filter(DBUser.telegram_id == tg_user_obj.id).first.return_value = None
    
    added_user_capture = None
    def capture_add(user_obj):
        nonlocal added_user_capture
        added_user_capture = user_obj
    mock_db_session.add.side_effect = capture_add

    await start_command(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "سلام Test!" in args[0]
    
    mock_db_session.add.assert_called_once()
    assert added_user_capture is not None
    assert added_user_capture.telegram_id == tg_user_obj.id
    assert added_user_capture.first_name == "Test"
    assert added_user_capture.username == "testuser"
    assert added_user_capture.subscription_tier == SubscriptionTier.FREE
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(added_user_capture)


@pytest.mark.asyncio
@patch('src.bot_handlers.get_db')
async def test_start_command_existing_user(mock_get_db, mock_db_session, mock_update_context):
    mock_get_db.return_value = iter([mock_db_session])
    update, context, tg_user_obj = mock_update_context

    existing_db_user = DBUser(
        telegram_id=tg_user_obj.id, 
        first_name="OldName", 
        username="oldusername",
        language_code="fr"
    )
    mock_db_session.query(DBUser).filter(DBUser.telegram_id == tg_user_obj.id).first.return_value = existing_db_user

    await start_command(update, context)

    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "سلام Test!" in args[0] 

    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(existing_db_user)
    
    assert existing_db_user.first_name == "Test"
    assert existing_db_user.username == "testuser"
    assert existing_db_user.language_code == "en"


@pytest.mark.asyncio
async def test_help_command(mock_update_context):
    update, context, _ = mock_update_context
    update.message.text = "/help"

    await help_command(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "دستورات موجود" in args[0]

@pytest.mark.asyncio
async def test_privacy_command(mock_update_context):
    update, context, _ = mock_update_context
    update.message.text = "/privacy"

    await privacy_command(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "سیاست حریم خصوصی" in args[0]

@pytest.mark.asyncio
@patch('src.bot_handlers.get_db')
async def test_text_message_handler(mock_get_db, mock_db_session, mock_update_context):
    mock_get_db.return_value = iter([mock_db_session])
    update, context, tg_user_obj = mock_update_context
    test_text_msg = "سلام، این یک پیام تست است."
    update.message.text = test_text_msg

    mock_db_session.query(DBUser).filter(DBUser.telegram_id == tg_user_obj.id).first.return_value = DBUser(telegram_id=tg_user_obj.id, first_name="Test")

    await text_message_handler(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "پیام شما دریافت شد" in args[0]
    assert test_text_msg in args[0]

# Test for get_or_create_user directly (optional, as it's tested via start_command)
# These tests remain synchronous as get_or_create_user is synchronous
@patch('src.bot_handlers.get_db')
@patch('src.bot_handlers.settings') # Mock settings for default language
def test_get_or_create_user_new(mock_settings, mock_get_db, mock_db_session):
    mock_get_db.return_value = iter([mock_db_session])
    mock_settings.DEFAULT_LANGUAGE = 'fa' # Set a default for the test
    mock_db_session.query(DBUser).filter(DBUser.telegram_id == 999).first.return_value = None
    
    added_user = None
    def capture_add(user):
        nonlocal added_user
        added_user = user
    mock_db_session.add.side_effect = capture_add

    # Test with explicit language_code
    user1 = get_or_create_user(999, "New", "User", "newbie", "de")
    assert user1 is not None
    mock_db_session.add.assert_called_once()
    assert added_user.telegram_id == 999
    assert added_user.first_name == "New"
    assert added_user.username == "newbie"
    assert added_user.language_code == "de"
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(added_user)

    # Reset mocks for next call in the same test
    mock_db_session.reset_mock()
    mock_db_session.query(DBUser).filter(DBUser.telegram_id == 1000).first.return_value = None
    added_user = None # Reset capture

    # Test with default language_code (None passed)
    user2 = get_or_create_user(1000, "DefaultLang", username="defusr")
    assert user2 is not None
    mock_db_session.add.assert_called_once()
    assert added_user.telegram_id == 1000
    assert added_user.language_code == 'fa' # Should use mocked settings.DEFAULT_LANGUAGE
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(added_user)


@patch('src.bot_handlers.get_db')
@patch('src.bot_handlers.settings')
def test_get_or_create_user_existing_no_update(mock_settings, mock_get_db, mock_db_session):
    mock_get_db.return_value = iter([mock_db_session])
    mock_settings.DEFAULT_LANGUAGE = 'fa'
    existing_user = DBUser(telegram_id=777, first_name="Exists", username="existinguser", language_code="fa")
    mock_db_session.query(DBUser).filter(DBUser.telegram_id == 777).first.return_value = existing_user

    user = get_or_create_user(777, "Exists", None, "existinguser", "fa")

    assert user == existing_user
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()
    mock_db_session.refresh.assert_not_called()

@patch('src.bot_handlers.get_db')
@patch('src.bot_handlers.settings')
def test_get_or_create_user_existing_with_update(mock_settings, mock_get_db, mock_db_session):
    mock_get_db.return_value = iter([mock_db_session])
    mock_settings.DEFAULT_LANGUAGE = 'fa'
    existing_user = DBUser(telegram_id=888, first_name="OldFirst", last_name="OldLast", username="olduser", language_code="en")
    mock_db_session.query(DBUser).filter(DBUser.telegram_id == 888).first.return_value = existing_user

    user = get_or_create_user(888, "NewFirst", "NewLast", "newuser", "de")

    assert user == existing_user
    assert user.first_name == "NewFirst"
    assert user.last_name == "NewLast"
    assert user.username == "newuser"
    assert user.language_code == "de"
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(existing_user) 