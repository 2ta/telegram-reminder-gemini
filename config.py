import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")

DATABASE_URL = "sqlite:///reminders.db"

# Persian Messages
MSG_CONFIRMATION = "باشه، یادآوری تنظیم شد.\n📝 متن: {task}\n⏰ زمان: {date}، ساعت {time}{recurrence_info}"
MSG_FAILURE_EXTRACTION = "متأسفانه نتوانستم جزئیات یادآوری را از پیام شما دریافت کنم. لطفاً واضح‌تر بیان کنید چه زمانی و برای چه کاری نیاز به یادآوری دارید."
MSG_REMINDER_NOTIFICATION = "🔔 یادآوری: {task}"
MSG_WELCOME = "سلام! من ربات یادآور شما هستم. می‌توانید با ارسال پیام متنی یا صوتی، یادآوری تنظیم کنید یا با دستور /list لیست یادآورهای خود را ببینید."
MSG_PROCESSING_VOICE = "در حال پردازش پیام صوتی شما..."
MSG_STT_FAILED = "متأسفانه نتوانستم پیام صوتی شما را به متن تبدیل کنم."
MSG_NLU_ERROR = "خطایی در پردازش درخواست شما با سرویس زبان رخ داد. لطفاً بعداً تلاش کنید."
MSG_DATE_PARSE_ERROR = "نتوانستم تاریخ یا زمان را از پیام شما استخراج کنم. لطفاً تاریخ را به فرمت شمسی (مانند ۲۲ اردیبهشت ۱۴۰۴) و زمان را (مانند ۱۷:۳۰) مشخص کنید."
MSG_REMINDER_IN_PAST = "متاسفانه نمی‌توانم برای گذشته یادآوری تنظیم کنم. تاریخ {date} ساعت {time} گذشته است."

# Interactive messages (Persian)
MSG_REQUEST_TASK = "چه چیزی را می‌خواهی بهت یادآوری کنم؟"
MSG_REQUEST_FULL_DATETIME = "چه زمانی می‌خوای یادت بندازم؟"
MSG_REQUEST_TIME_ONLY = "برای چه ساعتی می‌خواهی تنظیم بشه؟"
MSG_CONFIRM_DEFAULT_TIME = "باشه، یادآوری تنظیم شد.\n📝 متن: {task}\n⏰ زمان: {date}، ساعت ۹:۰۰ تنظیم شد.\nولی اگه ساعت دیگه‌ای رو می‌خوای بهم بگو؟"
MSG_ASK_AM_PM = "{time_hour} ظهر یا شب؟"
MSG_CONFIRMATION_UPDATE = "باشه، به‌روز شد.\n📝 متن: {task}\n⏰ زمان: {date}، ساعت {time}{recurrence_info}"

MSG_LIST_HEADER = "📅 یادآورهای شما:"
MSG_LIST_ITEM = "{index}. «{task}» – {date}، ساعت {time}{recurrence_info}"
MSG_LIST_EMPTY = "شما در حال حاضر هیچ یادآور فعالی ندارید."
MSG_SELECT_FOR_DELETE = "شماره یادآوری که می‌خواهید حذف کنید را وارد کنید (یا 'لغو' برای انصراف):"
MSG_REMINDER_DELETED = "🗑️ یادآور «{task}» حذف شد."
MSG_REMINDER_NOT_FOUND_FOR_ACTION = "یادآوری با این شماره پیدا نشد یا عملیات لغو شد."
MSG_INVALID_SELECTION = "انتخاب نامعتبر. لطفاً یک شماره از لیست وارد کنید یا 'لغو' بگویید."
MSG_CANCELLED = "عملیات لغو شد."
MSG_GENERAL_ERROR = "متاسفانه خطایی در سرور ربات رخ داد. لطفاً دوباره تلاش کنید."
MSG_EDIT_REMINDER_FIELD_CHOICE = "چه چیزی رو می‌خوای تغییر بدی؟ متن یا زمان؟"
MSG_EDIT_REMINDER_UPDATED = "باشه، به‌روزرسانی شد.\n📝 متن: {task}\n⏰ زمان جدید: {date}، ساعت {time}"
MSG_RECURRING_REMINDER_CONFIRMATION = "حتماً. یادآوری {recurring_type} تنظیم شد.\n📝 متن: {task}\n⏰ زمان: {recurring_time}"

if not all([TELEGRAM_BOT_TOKEN, GOOGLE_APPLICATION_CREDENTIALS, GEMINI_PROJECT_ID, GEMINI_LOCATION, GEMINI_MODEL_NAME]):
    raise ValueError("One or more critical environment variables are not set. Check your .env file and ensure GOOGLE_APPLICATION_CREDENTIALS path is correct.")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS