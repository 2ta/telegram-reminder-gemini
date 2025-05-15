import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Google Cloud Credentials
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Gemini Configuration
GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.0-pro-001")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///reminders.db")

# Payment Configuration (Zibal)
ZIBAL_MERCHANT_KEY = os.getenv("ZIBAL_MERCHANT_KEY")
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "https://yourdomain.com/bot")  # Base URL for callbacks
PAYMENT_AMOUNT = int(os.getenv("PAYMENT_AMOUNT", "100000"))  # Default: 10,000 Rials (100,000 is actually 10,000 Toman)

# Logging Configuration
LOG_FILE = "bot.log"
LOG_LEVEL = "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL

# --- Persian Messages ---
# General
MSG_WELCOME = "سلام! من یک ربات یادآور هستم. برای تنظیم یادآور، کافیه بهم بگی. مثلا: «یادم بنداز فردا ساعت ۱۰ صبح به علی زنگ بزنم» یا «جلسه تیم، دوشنبه ساعت ۳ بعد از ظهر»."
MSG_HELP = """راهنما:
- برای تنظیم یادآور: فقط کافیه بهم بگی چی رو و کی بهت یادآوری کنم. مثلا:
  - "یادم بنداز فردا ساعت ۱۰ صبح به دوستم زنگ بزنم"
  - "جلسه پروژه، پس‌فردا ساعت ۳ بعد از ظهر"
  - "خرید هفتگی، جمعه ساعت ۱۱"
  - "یادم بنداز یک ساعت دیگه استراحت کنم"
  - "یادم بنداز به مادرم زنگ بزنم بعد از اینکه به خانه رسیدم" (یادآور نسبی)
- برای دیدن لیست یادآورهای فعال: بگو "یادآورهای من"
- برای حذف یا ویرایش یادآور: از دکمه‌های زیر لیست یادآورها استفاده کن.
- برای لغو عملیات فعلی: بگو "لغو"
- برای تعویق یادآور: بعد از دریافت اعلان، می‌توانید با ارسال زمان جدید (مثلا "نیم ساعت دیگه") آن را به تعویق بیندازید.
- برای ارتقا به نسخه حرفه‌ای: دستور /pay را ارسال کنید.
"""
MSG_CANCELLED = "عملیات لغو شد."
MSG_DONE = "انجام شد."
MSG_LIST_REMINDERS_HEADER = "⏰ لیست یادآورهای فعال شما:"
MSG_NO_REMINDERS = "شما هیچ یادآور فعالی ندارید."
MSG_REMINDER_DELETED = "یادآور «{task}» حذف شد." # Added {task} placeholder
MSG_REMINDER_NOTIFICATION = "🔔 یادآوری: {task}"
MSG_REMINDER_NOT_FOUND_FOR_ACTION = "یادآور مورد نظر برای انجام این عملیات یافت نشد یا دیگر فعال نیست."
MSG_SELECT_REMINDER_TO_DELETE = "کدام یادآور را می‌خواهید حذف کنید؟ شماره‌اش را وارد کنید یا \'لغو\' بگویید."
MSG_SELECT_REMINDER_TO_EDIT = "کدام یادآور را می‌خواهید ویرایش کنید؟ شماره‌اش را وارد کنید یا \'لغو\' بگویید."
MSG_INVALID_SELECTION = "انتخاب نامعتبر. لطفاً یک شماره از لیست وارد کنید یا \'لغو\' بگویید."
MSG_FAILURE_PERMISSION_DENIED = "متاسفانه اجازه دسترسی به فایل صوتی داده نشد."
MSG_VOICE_TOO_LONG = "فایل صوتی خیلی طولانی است. لطفاً یک پیام صوتی کوتاه‌تر ارسال کنید (حداکثر ۱ دقیقه)."
MSG_VOICE_PROCESSING_ERROR = "متاسفانه در پردازش پیام صوتی شما خطایی رخ داد."
MSG_VOICE_UNRECOGNIZED = "متاسفانه نتوانستم صحبت شما را متوجه شوم. لطفاً واضح‌تر صحبت کنید یا تایپ کنید."
MSG_VOICE_SUCCESS_BUT_NLU_FAILED = "پیام صوتی شما با موفقیت به متن تبدیل شد، اما در درک منظور شما مشکلی پیش آمد."
MSG_PROCESSING_VOICE = "در حال پردازش پیام صوتی شما..."

# Payment Messages
MSG_PAYMENT_PROMPT = "💎 برای ارتقا به نسخه حرفه‌ای و استفاده از امکانات بیشتر، می‌توانید با پرداخت {amount} تومان اشتراک ۳۰ روزه دریافت کنید."
MSG_PAYMENT_BUTTON = "💳 پرداخت و ارتقا"
MSG_PAYMENT_SUCCESS = "✅ پرداخت شما با موفقیت انجام شد! اکنون شما کاربر ویژه هستید و می‌توانید از تمامی امکانات ربات استفاده کنید.\n\nاشتراک شما تا تاریخ {expiry_date} معتبر است."
MSG_PAYMENT_FAILED = "❌ پرداخت ناموفق بود. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
MSG_PAYMENT_CANCELLED = "⚠️ پرداخت لغو شد. هر زمان که تمایل داشتید می‌توانید با ارسال دستور /pay اقدام به پرداخت نمایید."
MSG_PAYMENT_ERROR = "⚠️ خطا در ارتباط با درگاه پرداخت. لطفاً بعداً دوباره تلاش کنید."
MSG_ALREADY_PREMIUM = "✨ شما در حال حاضر کاربر ویژه هستید! اشتراک شما تا تاریخ {expiry_date} معتبر است."

# Reminder Setup Flow
MSG_CONFIRMATION = "باشه، یادآوری تنظیم شد.\\n📝 متن: {task}\\n⏰ زمان: {date}، ساعت {time}{recurrence_info}"
MSG_RECURRING_REMINDER_CONFIRMATION = "حتماً. یادآوری {recurring_type} تنظیم شد.\\n📝 متن: {task}\\n⏰ زمان: {recurring_time}"
MSG_REQUEST_TASK = "چه کاری را می‌خواهی بهت یادآوری کنم؟"
MSG_REQUEST_FULL_DATETIME = "باشه، چه زمانی بهت یادآوری کنم؟ (مثلاً: فردا ساعت ۱۰ صبح، یا ۲۵ اسفند ساعت ۱۵:۳۰)"
MSG_REQUEST_TIME_ONLY = "ساعت چند؟"
MSG_CONFIRM_DEFAULT_TIME = "یادآوری برای «{task}» در تاریخ {date}، ساعت ۹ صبح تنظیم شد. برای تغییر ساعت، زمان جدید را وارد کنید (مثلاً ۱۷:۳۰)، در غیر این صورت «تایید» را بزنید یا منتظر بمانید."
MSG_INVALID_DATETIME = "متاسفانه نتوانستم این تاریخ و زمان را متوجه شوم. لطفاً به شکل دیگری بیان کنید (مثلاً: فردا ساعت ۱۰ صبح، یا ۲۵ اسفند ساعت ۱۵:۳۰، یا ۳۰ دقیقه دیگه)."
MSG_DATETIME_IN_PAST = "این زمان در گذشته است! لطفاً یک زمان در آینده انتخاب کنید." # Corrected from MSG_REMINDER_IN_PAST
MSG_NLU_ERROR = "متاسفانه در درک منظور شما با سرویس زبان مشکلی پیش آمد. لطفاً کمی واضح‌تر و کامل‌تر بیان کنید یا بعداً تلاش کنید."
MSG_FAILURE_EXTRACTION = "متأسفانه نتوانستم جزئیات یادآوری را از پیام شما دریافت کنم. لطفاً واضح‌تر بیان کنید چه زمانی و برای چه کاری نیاز به یادآوری دارید."
MSG_ASK_AM_PM = "ساعت {time_hour} صبح یا بعد از ظهر؟ (مثلاً: ۱۰ صبح، یا ۲ ظهر)"
MSG_INVALID_AM_PM = "متوجه نشدم. لطفاً مشخص کنید صبح است یا بعد از ظهر (مثلاً با گفتن \\\'صبح\\\' یا \\\'عصر\\\')."

# Relative Reminders
MSG_RELATIVE_REMINDER_CONFIRMATION = "باشه، یادآوری برای «{task}» تنظیم شد که {relative_offset_description} بعد از «{primary_event_task}» انجام شود، در تاریخ {date} ساعت {time}."
MSG_REQUEST_PRIMARY_EVENT_TIME = "زمان «{primary_event_task}» کی هست؟ (مثلاً: امروز ساعت ۵ عصر، یا فردا ساعت ۱۰ صبح)"

# Edit Flow
MSG_REQUEST_NEW_TASK = "متن جدید یادآور چی باشه؟"
MSG_REQUEST_NEW_DATETIME = "زمان جدید یادآور کی باشه؟ (تاریخ و ساعت کامل)"
MSG_EDIT_REMINDER_UPDATED = "باشه، به‌روزرسانی شد.\\n📝 متن: {task}\\n⏰ زمان جدید: {date}، ساعت {time}"
MSG_EDIT_REMINDER_FIELD_CHOICE = "کدام بخش از یادآور را می‌خواهید ویرایش کنید؟" # Corrected version
MSG_NO_REMINDER_TO_EDIT = "یادآوری‌ای برای ویرایش پیدا نشد. لطفاً ابتدا یک یادآور تنظیم کنید یا لیست یادآورهای خود را ببینید." # Ensured presence

# Snooze / Re-reminder
MSG_SNOOZE_CONFIRMATION = "باشه، یادآوری «{task}» برای {time} مجدداً تنظیم شد."
MSG_SNOOZE_FAILURE_NO_CONTEXT = "متاسفم، متوجه نشدم کدام یادآوری را می‌خواهید به تعویق بیندازید. لطفاً ابتدا منتظر اعلان یادآوری بمانید."
MSG_SNOOZE_FAILURE_NLU = "متوجه نشدم برای چه زمانی می‌خواهید به تعویق بیندازید. لطفاً زمان دقیق (مثلاً \'نیم ساعت دیگه\'، \'فردا ساعت ۱۰ صبح\') یا \'لغو\' را ارسال کنید."
MSG_SNOOZE_ASK_TIME = "برای چه زمانی می‌خواهید یادآوری را به تعویق بیندازم؟"

# General Errors / Status
MSG_GENERAL_ERROR = "متأسفانه خطایی در سیستم رخ داد. لطفاً بعداً تلاش کنید." # Corrected version

# Ensure all required environment variables are loaded
required_vars = [
    TELEGRAM_BOT_TOKEN,
    GOOGLE_APPLICATION_CREDENTIALS,
    GEMINI_PROJECT_ID,
    GEMINI_LOCATION,
    GEMINI_MODEL_NAME,
    ZIBAL_MERCHANT_KEY
]

if not all([var for var in required_vars if var is not None]):
    # Simplified error message for startup
    print("FATAL ERROR: Required environment variables are missing. Please check your .env file or environment configuration.")
    print(f"TELEGRAM_BOT_TOKEN: {'OK' if TELEGRAM_BOT_TOKEN else 'MISSING'}")
    print(f"GOOGLE_APPLICATION_CREDENTIALS: {'OK' if GOOGLE_APPLICATION_CREDENTIALS else 'MISSING'}")
    print(f"GEMINI_PROJECT_ID: {'OK' if GEMINI_PROJECT_ID else 'MISSING'}")
    print(f"GEMINI_LOCATION: {'OK' if GEMINI_LOCATION else 'MISSING'}")
    print(f"GEMINI_MODEL_NAME: {'OK' if GEMINI_MODEL_NAME else 'MISSING'}")
    print(f"ZIBAL_MERCHANT_KEY: {'OK' if ZIBAL_MERCHANT_KEY else 'MISSING'}")
    exit(1)

# Validate that GOOGLE_APPLICATION_CREDENTIALS points to an existing file
if GOOGLE_APPLICATION_CREDENTIALS and not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS): # Check if set before checking path
    print(f"FATAL ERROR: Google Application Credentials file not found at: {GOOGLE_APPLICATION_CREDENTIALS}")
    exit(1)
elif not GOOGLE_APPLICATION_CREDENTIALS: # Already covered by the all() check, but good for explicit message
     print(f"FATAL ERROR: GOOGLE_APPLICATION_CREDENTIALS is not set.")
     exit(1)


# Fallback for older python-telegram-bot versions if DispatcherHandlerStop is not available
try:
    from telegram.ext import DispatcherHandlerStop
    USE_DISPATCHER_HANDLER_STOP = True
except ImportError:
    USE_DISPATCHER_HANDLER_STOP = False
    print("WARNING: DispatcherHandlerStop not found. Snooze functionality might be limited or behave differently.")