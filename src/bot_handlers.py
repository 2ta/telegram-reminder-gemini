import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from langchain_core.messages import HumanMessage # For message history
from typing import Dict, Any

from config.config import settings
from src.database import get_db
from src.models import User, SubscriptionTier
from src.voice_utils import process_voice_message
from src.graph import lang_graph_app # Import the compiled graph

logger = logging.getLogger(__name__)

# --- User Management ---
def get_or_create_user(telegram_user_id: int, first_name: str, last_name: str = None, username: str = None, language_code: str = None) -> User:
    """Gets an existing user or creates a new one if not found."""
    db = next(get_db())
    user = db.query(User).filter(User.telegram_id == telegram_user_id).first()
    if not user:
        logger.info(f"Creating new user for telegram_id: {telegram_user_id}")
        user = User(
            telegram_id=telegram_user_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            language_code=language_code or settings.DEFAULT_LANGUAGE,
            subscription_tier=SubscriptionTier.FREE # Default tier
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif (user.first_name != first_name or
          user.last_name != last_name or
          user.username != username or
          (language_code and user.language_code != language_code)):
        logger.info(f"Updating user info for telegram_id: {telegram_user_id}")
        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        if language_code: # Only update language if provided and different
            user.language_code = language_code
        db.commit()
        db.refresh(user)
    return user

# --- Graph Invocation ---
async def invoke_graph_with_input(input_text: str, user_id: int, message_type: str) -> Dict[str, Any]:
    """Invokes the LangGraph app with the given input and returns the response text and keyboard markup."""
    logger.info(f"Invoking graph for user_id {user_id}, type '{message_type}', input: '{input_text}'")
    
    # Configuration for the graph invocation, using user_id as thread_id for conversation memory
    config = {"configurable": {"thread_id": str(user_id)}}
    
    # Prepare the input for the graph state
    graph_input = {
        "input_text": input_text,
        "user_id": user_id,
        "message_type": message_type,
        "messages": [HumanMessage(content=input_text)], # Add current message to history
        "chat_id": user_id  # Setting chat_id = user_id for private chats
    }
    
    try:
        # Since all graph nodes are defined as async functions, we need to use ainvoke
        final_state = await lang_graph_app.ainvoke(graph_input, config=config)

        response_text = final_state.get("response_text", "Sorry, no response was received.")
        response_keyboard_markup = final_state.get("response_keyboard_markup") # Can be None
        
        logger.info(f"Graph for user_id {user_id} responded with text: '{response_text}' and keyboard: {bool(response_keyboard_markup)}")
        return {"text": response_text, "keyboard_markup": response_keyboard_markup}
    except KeyError as e:
        logger.error(f"KeyError in LangGraph for user_id {user_id}: {e}", exc_info=True)
        return {"text": f"Processing error: Required information '{e}' was not found.", "keyboard_markup": None}
    except ValueError as e:
        logger.error(f"ValueError in LangGraph for user_id {user_id}: {e}", exc_info=True)
        return {"text": f"Input value error: {str(e)}", "keyboard_markup": None}
    except Exception as e:
        logger.error(f"Error invoking LangGraph for user_id {user_id}: {e}", exc_info=True)
        return {"text": "Sorry, an error occurred while processing your request. Please try /start again.", "keyboard_markup": None}

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    tg_user = update.effective_user
    logger.info(f"/start command received from user_id: {tg_user.id}, username: {tg_user.username}")

    user = get_or_create_user(
        telegram_user_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=tg_user.username,
        language_code=tg_user.language_code
    )

    welcome_message = (
        f"Hello {user.first_name}! Welcome to the Reminder Bot.\n"
        "I can help you remember your important tasks and events.\n"
        "To see available commands, use /help."
    )
    # Example of a custom keyboard
    # keyboard = [[KeyboardButton("/new_reminder"), KeyboardButton("/my_reminders")]]
    # reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    # await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command."""
    logger.info(f"/help command received from user_id: {update.effective_user.id}")
    help_text = (
        "Available commands:\n"
        "/start - Start using the bot and register\n"
        "/help - Show this help message\n"

        "\n"
        "You can send your reminders as text or voice messages.\n"
        "Example to create a reminder:\n"
        "'Remind me to call the sales team tomorrow at 10am'"
    )
    await update.message.reply_text(help_text)




# --- Message Handlers ---
async def generic_message_processor(update: Update, context: ContextTypes.DEFAULT_TYPE, input_text: str, message_type: str) -> None:
    """Generic processor for text and transcribed voice messages using LangGraph."""
    user = update.effective_user
    db_user = get_or_create_user(telegram_user_id=user.id, first_name=user.first_name, last_name=user.last_name, username=user.username, language_code=user.language_code)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    response_data = await invoke_graph_with_input(input_text, db_user.id, message_type)
    response_text = response_data.get("text", "خطایی رخ داده است.")
    keyboard_markup = response_data.get("keyboard_markup") # This can be None
    
    # The python-telegram-bot library expects an InlineKeyboardMarkup object or None
    # The graph currently passes a dict representation. We need to convert it.
    # However, for now, let's assume the library can handle the dict if it's structured correctly
    # as per InlineKeyboardMarkup.to_dict() if it's indeed a dict.
    # If it fails, we'll need to explicitly create InlineKeyboardMarkup(keyboard_markup["inline_keyboard"]).
    
    await update.message.reply_text(response_text, reply_markup=keyboard_markup)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general text messages by passing them to the LangGraph agent."""
    logger.info(f"Text message from {update.effective_user.id}: '{update.message.text}', forwarding to graph.")
    await generic_message_processor(update, context, update.message.text, "text")

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles voice messages by transcribing and then passing to LangGraph."""
    user_id = update.effective_user.id
    logger.info(f"Voice message received from user_id: {user_id}, attempting transcription.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    transcribed_text = await process_voice_message(update, context)

    if transcribed_text:
        logger.info(f"Voice message from user {user_id} transcribed to: '{transcribed_text}', forwarding to graph.")
        await generic_message_processor(update, context, transcribed_text, "voice_transcribed")
    else:
        logger.warning(f"Voice message from user {user_id} could not be transcribed. No graph invocation.")
        # process_voice_message already sends a message to user on failure

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("متاسفانه مشکلی در پردازش درخواست شما پیش آمده است.")
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

# --- Handler Registration (example, to be used in bot_runner.py) ---
# def register_handlers(application):
#     application.add_handler(CommandHandler("start", start_command))
#     application.add_handler(CommandHandler("help", help_command))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
#     application.add_error_handler(error_handler) 