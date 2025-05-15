import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from config.config import settings
from src.database import get_db
from src.models import User, SubscriptionTier

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
        "برای ایجاد یک یادآور جدید، کافیست آن را به صورت متنی برای من ارسال کنید. مثال:\n"
        "'یادآوری کن فردا ساعت ۱۰ صبح جلسه با تیم فروش'\n"
        "'پس فردا ساعت ۳ بعد از ظهر خرید از فروشگاه'"
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
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general text messages (potential reminders or other interactions)."""
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Text message received from user_id: {user_id}. Message: '{text}'")

    # For now, just acknowledge. LangGraph will handle this later.
    await update.message.reply_text(f"پیام شما دریافت شد: '{text}'. به زودی این بخش هوشمندتر خواهد شد!")

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    # Optionally, notify user or admin
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("متاسفانه مشکلی در پردازش درخواست شما پیش آمده است.")

# --- Handler Registration (example, to be used in bot_runner.py) ---
# def register_handlers(application):
#     application.add_handler(CommandHandler("start", start_command))
#     application.add_handler(CommandHandler("help", help_command))
#     application.add_handler(CommandHandler("privacy", privacy_command))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
#     application.add_error_handler(error_handler) 