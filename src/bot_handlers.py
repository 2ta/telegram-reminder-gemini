import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from langgraph.graph.message import HumanMessage # For message history

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
async def invoke_graph_with_input(input_text: str, user_id: int, message_type: str) -> str:
    """Invokes the LangGraph app with the given input and returns the response."""
    logger.info(f"Invoking graph for user_id {user_id}, type '{message_type}', input: '{input_text}'")
    
    # Configuration for the graph invocation, using user_id as thread_id for conversation memory
    config = {"configurable": {"thread_id": str(user_id)}}
    
    # Prepare the input for the graph state
    graph_input = {
        "input_text": input_text,
        "user_id": user_id,
        "message_type": message_type,
        "messages": [HumanMessage(content=input_text)] # Add current message to history
    }
    
    try:
        # Asynchronously invoke the graph
        # Note: lang_graph_app.ainvoke might be available in newer LangGraph versions for true async node execution
        # For now, if graph nodes are async, ainvoke should handle it. If nodes are sync, this will run them in executor.
        # If lang_graph_app itself is not async-native for invoke, we might need to run it in an executor.
        # For now, assuming lang_graph_app.invoke can be awaited if the underlying execution is async.
        # Let's assume a standard invoke and handle async execution within nodes if necessary, or use `run_in_executor` for the whole invoke call.
        # Correction: graph.invoke is synchronous. Use `app.ainvoke` if available and nodes are async.
        # If nodes are async, StateGraph handles running them in an event loop.
        # SqliteSaver is sync, so ainvoke might have issues with it if not handled by LangGraph.
        # Let's use ainvoke and ensure a new event loop if needed or rely on PTB's loop.

        # Using app.invoke for now as it's standard. If performance issues arise, look into ainvoke or running invoke in thread.
        # final_state = await asyncio.to_thread(lang_graph_app.invoke, graph_input, config=config) # Example for sync invoke in async
        
        # PTB runs handlers in its own asyncio loop. Langchain graph.invoke is sync.
        # To avoid blocking PTB's loop, run sync LangGraph invoke in a separate thread.
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(None, lang_graph_app.invoke, graph_input, config=config)

        response_text = final_state.get("response_text", "متاسفانه پاسخی دریافت نشد.")
        logger.info(f"Graph for user_id {user_id} responded: '{response_text}'")
        return response_text
    except Exception as e:
        logger.error(f"Error invoking LangGraph for user_id {user_id}: {e}", exc_info=True)
        return "متاسفانه در پردازش درخواست شما از طریق گراف خطایی رخ داد."

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
        f"سلام {user.first_name}! به ربات یادآور خوش آمدید.\n"
        "من به شما کمک می‌کنم تا کارهایتان را به موقع به یاد بیاورید.\n"
        "برای مشاهده دستورات موجود، از /help استفاده کنید."
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
        "دستورات موجود:\n"
        "/start - شروع به کار با ربات و ثبت‌نام\n"
        "/help - نمایش این پیام راهنما\n"
        "/privacy - مشاهده سیاست‌های حریم خصوصی\n"
        "\n"
        "می‌توانید پیام‌های خود را به صورت متنی یا صوتی ارسال کنید.\n"
        "مثال برای ایجاد یادآور:\n"
        "'یادآوری کن فردا ساعت ۱۰ صبح جلسه با تیم فروش'"
    )
    await update.message.reply_text(help_text)

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /privacy command."""
    logger.info(f"/privacy command received from user_id: {update.effective_user.id}")
    # TODO: Replace with actual privacy policy link or text from a resource file
    privacy_text = (
        "سیاست حریم خصوصی ربات یادآور:\n"
        "ما به حریم خصوصی شما احترام می‌گذاریم. اطلاعات شما فقط برای ارائه خدمات یادآوری استفاده می‌شود و با هیچ شخص ثالثی به اشتراک گذاشته نخواهد شد.\n"
        "برای اطلاعات بیشتر، لطفاً به [لینک کامل سیاست حریم خصوصی] مراجعه کنید."
    )
    await update.message.reply_text(privacy_text)


# --- Message Handlers ---
async def generic_message_processor(update: Update, context: ContextTypes.DEFAULT_TYPE, input_text: str, message_type: str) -> None:
    """Generic processor for text and transcribed voice messages using LangGraph."""
    user = update.effective_user
    db_user = get_or_create_user(telegram_id=user.id, first_name=user.first_name, last_name=user.last_name, username=user.username, language_code=user.language_code)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    response_from_graph = await invoke_graph_with_input(input_text, db_user.id, message_type)
    await update.message.reply_text(response_from_graph)

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
#     application.add_handler(CommandHandler("privacy", privacy_command))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
#     application.add_error_handler(error_handler) 