import os
from typing import Optional, Union, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, AnyHttpUrl

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Telegram API Configuration
    TELEGRAM_BOT_TOKEN: str

    # Database Configuration
    DATABASE_URL: Union[PostgresDsn, str] = "sqlite:///./default.db"
    DATABASE_URL_TEST: Optional[Union[PostgresDsn, str]] = "sqlite:///./test.db"

    # Google Cloud / Gemini Configuration
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GEMINI_PROJECT_ID: Optional[str] = None
    GEMINI_LOCATION: Optional[str] = None
    GEMINI_MODEL_NAME: str = "gemini-1.0-pro-001"
    GEMINI_API_KEY: Optional[str] = None

    # Payment Gateway (Zibal) Configuration
    ZIBAL_MERCHANT_KEY: Optional[str] = None
    PAYMENT_CALLBACK_URL_BASE: Optional[AnyHttpUrl] = None

    # Logging Configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FILE_PATH: str = "logs/bot.log"
    LOG_FILE_MAX_BYTES: int = 1024 * 1024 * 5  # 5MB
    LOG_FILE_BACKUP_COUNT: int = 3

    # Other application settings
    DEFAULT_LANGUAGE: str = "fa"

    # Tier configurations for reminders
    MAX_REMINDERS_FREE_TIER: int = Field(default=5, description="Maximum active reminders for free tier users")
    MAX_REMINDERS_PREMIUM_TIER: int = Field(default=100, description="Maximum active reminders for premium tier users")
    REMINDERS_PER_PAGE: int = Field(default=5, description="Number of reminders to show per page in lists")

    # Environment setting (dev, test, prod)
    APP_ENV: Literal["development", "testing", "production"] = "development"

settings = Settings()

# --- Persian Messages (Module-level constants) ---
MSG_WELCOME: str = (
    "به ربات یادآور خوش آمدید! برای ایجاد یادآور، کافیست پیام خود را ارسال کنید. "
    "مثلاً: 'یادآوری کن فردا ساعت ۱۰ صبح جلسه دارم'. برای راهنمایی بیشتر از دستور /help استفاده کنید."
)
MSG_HELP: str = (
    "راهنمای ربات یادآور:\n"
    "- برای ایجاد یادآور: مثلا بنویسید: 'یادآوری کن فردا ساعت ۱۰ صبح جلسه دارم'\n"
    "- برای دیدن یادآورها: /reminders یا 'یادآورهای من'\n"
    "- برای لغو عملیات فعلی: /cancel\n"
    "- برای دریافت این راهنما: /help\n"
    "- برای اطلاع از وضعیت اشتراک و پرداخت: /pay\n"
    "- برای مشاهده سیاست حفظ حریم خصوصی: /privacy"
)
MSG_PRIVACY_POLICY: str = (
    "سیاست حفظ حریم خصوصی ربات یادآور:\n\n"
    "ما به حریم خصوصی شما احترام می‌گذاریم.\n"
    "1. اطلاعات جمع‌آوری شده: \n"
    "   - شناسه کاربری تلگرام و شناسه چت: برای ارائه خدمات و ارسال یادآورها.\n"
    "   - نام کاربری و نام (اختیاری): برای شخصی‌سازی تجربه شما.\n"
    "   - محتوای یادآورها: برای ذخیره و ارسال یادآورهای شما.\n"
    "   - فایل‌های صوتی (در صورت ارسال): برای تبدیل به متن و ایجاد یادآور.\n"
    "2. استفاده از اطلاعات:\n"
    "   - اطلاعات شما صرفاً برای عملکرد صحیح ربات و ارائه خدمات یادآوری استفاده می‌شود.\n"
    "   - ما اطلاعات شما را با هیچ شخص ثالثی به اشتراک نمی‌گذاریم، مگر در مواردی که قانون ایجاب کند.\n"
    "3. ذخیره‌سازی اطلاعات:\n"
    "   - اطلاعات یادآورها و فایل‌های صوتی موقتاً تا زمان پردازش و ارسال یادآور ذخیره می‌شوند.\n"
    "   - فایل‌های صوتی پس از پردازش و تبدیل به متن، در اسرع وقت حذف می‌گردند.\n"
    "4. امنیت:\n"
    "   - ما تلاش می‌کنیم تا از اطلاعات شما با استفاده از روش‌های امنیتی مناسب محافظت کنیم.\n"
    "5. تغییرات در سیاست حفظ حریم خصوصی:\n"
    "   - هرگونه تغییر در این سیاست از طریق همین ربات به اطلاع شما خواهد رسید.\n\n"
    "با استفاده از این ربات، شما با این سیاست موافقت می‌کنید."
)
MSG_PAYMENT_PROMPT: str = "برای دسترسی به امکانات ویژه و تعداد یادآورهای بیشتر، می‌توانید اشتراک خود را ارتقا دهید. هزینه اشتراک: {amount} تومان."


if __name__ == "__main__":
    print("Current Configuration Loaded via Pydantic:")
    print(settings.model_dump_json(indent=2))
    print("\nModule-level messages:")
    print(f"MSG_WELCOME: {MSG_WELCOME}")
    print(f"MSG_HELP: {MSG_HELP}")
    print(f"MSG_PRIVACY_POLICY: {MSG_PRIVACY_POLICY}")
    print(f"MSG_PAYMENT_PROMPT: {MSG_PAYMENT_PROMPT}")

# Message Constants
MSG_FILTER_DATE_PARSE_ERROR = "متاسفانه نتوانستم عبارت تاریخی \"{phrase}\" را برای فیلتر کردن متوجه شوم. لطفاً دوباره امتحان کنید."
MSG_FILTER_UNSUCCESSFUL = "نتوانستم فیلتر مشخص شده با عبارت \"{text}\" را اعمال کنم. لطفاً دوباره امتحان کنید یا عبارت دیگری به کار ببرید."
MSG_FILTERS_APPLIED = "فیلترهای زیر اعمال شدند: "
MSG_FILTER_NO_CRITERIA_FOUND = "عبارت \"{text}\" شامل معیار قابل تشخیصی برای فیلتر کردن نبود."
MSG_FILTER_NLU_ERROR = "خطایی در پردازش عبارت فیلتر \"{text}\" رخ داد. لطفاً دوباره امتحان کنید."
MSG_LIST_EMPTY_WITH_FILTERS = "هیچ یادآوری با فیلترهای اعمال شده یافت نشد."
MSG_LIST_HEADER_WITH_FILTERS = "یادآورهای شما (فیلتر شده):"

# General Messages
MSG_ERROR_GENERIC = "متاسفانه خطایی رخ داد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
MSG_SUCCESS_GENERIC = "عملیات با موفقیت انجام شد."
MSG_NOT_IMPLEMENTED_YET = "این قابلیت هنوز پیاده‌سازی نشده است. به زودی اضافه خواهد شد!"
MSG_PAYMENT_BUTTON = "پرداخت حق اشتراک"
MSG_PAYMENT_SUCCESS = "پرداخت شما با موفقیت انجام شد. اشتراک ویژه شما تا تاریخ {expiry_date} فعال شد."
MSG_PAYMENT_SUCCESS_GENERIC = "پرداخت شما با موفقیت انجام شد و اشتراک ویژه شما فعال شد."
MSG_PAYMENT_FAILED = "متاسفانه پرداخت شما ناموفق بود. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
MSG_PAYMENT_CANCELLED = "پرداخت توسط شما لغو شد."
MSG_PAYMENT_ALREADY_VERIFIED = "این پرداخت قبلاً تایید شده است."
MSG_PAYMENT_PENDING_VERIFICATION = "وضعیت پرداخت شما هنوز نامشخص است. لطفاً کمی صبر کنید و مجدداً بررسی نمایید."
MSG_PAYMENT_VERIFICATION_ERROR = "خطا در تایید پرداخت: {error}. اگر مبلغی از حساب شما کسر شده، طی ۷۲ ساعت آینده به حساب شما باز خواهد گشت."
MSG_PAYMENT_ERROR = "خطا در ایجاد لینک پرداخت. لطفاً دوباره تلاش کنید."
MSG_PAYMENT_CONFIG_ERROR = "خطا در تنظیمات پرداخت. لطفاً با مدیر ربات تماس بگیرید."

# Reminder specific messages
MSG_REMINDER_SET = "یادآور شما برای \"{task}\" در تاریخ {date} ساعت {time} تنظیم شد."
MSG_REMINDER_NOT_FOUND = "یادآور مورد نظر یافت نشد."
MSG_REMINDER_DELETED = "یادآور \"{task}\" حذف شد."
MSG_REMINDER_LIMIT_REACHED_FREE = "شما به حداکثر تعداد یادآورهای مجاز ({limit}) برای کاربران رایگان رسیده‌اید. برای ثبت یادآورهای بیشتر، لطفاً اشتراک خود را ویژه کنید."
MSG_REMINDER_LIMIT_REACHED_PREMIUM = "شما به حداکثر تعداد یادآورهای مجاز ({limit}) برای کاربران ویژه رسیده‌اید." 