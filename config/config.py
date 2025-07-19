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
    GEMINI_MODEL_NAME: str = "gemini-2.0-flash"
    GEMINI_API_KEY: Optional[str] = None

    # Payment Gateway (Stripe) Configuration
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    PAYMENT_CALLBACK_URL_BASE: Optional[str] = None

    # Logging Configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FILE_PATH: str = "logs/bot.log"
    LOG_FILE_MAX_BYTES: int = 1024 * 1024 * 5  # 5MB
    LOG_FILE_BACKUP_COUNT: int = 3

    # Other application settings
    DEFAULT_LANGUAGE: str = "en"

    # Tier configurations for reminders
    MAX_REMINDERS_FREE_TIER: int = Field(default=5, description="Maximum active reminders for free tier users")
    MAX_REMINDERS_PREMIUM_TIER: int = Field(default=100, description="Maximum active reminders for premium tier users")
    REMINDERS_PER_PAGE: int = Field(default=5, description="Number of reminders to show per page in lists")

    # Feature flags
    IGNORE_REMINDER_LIMITS: bool = Field(default=False, description="If True, ignores reminder limits for all users (development mode)")

    # Environment setting (dev, test, prod)
    APP_ENV: Literal["development", "testing", "production"] = "development"

    # Web Server Configuration for Legal Pages
    LEGAL_PAGES_BASE_URL: str = "http://45.77.155.59:8080"

settings = Settings()

# --- English Messages (Module-level constants) ---
MSG_WELCOME: str = (
    "Hello 👋\n"
    "Welcome to the Reminder Bot!\n\n"
    "Just send me a message or voice and tell me what to remind you about and when. For example:\n"
    "🗓 \"Remind me to message Ali tomorrow at 10 AM\"\n"
    "💊 \"Remind me to take my pills every day at 8 AM\"\n\n"
    "✨ Bot Features:\n"
    "- Create reminders by speaking or typing\n"
    "- Smart detection of date and time from your message\n"
    "- View and delete active reminders\n"
    "- (Coming soon) Set recurring reminders\n"
    "- (Coming soon) Payment and activation of 'Unlimited Reminders' subscription for more features\n\n"
    "In the free version, you can have up to 5 active reminders."
)



MSG_PAYMENT_PROMPT: str = "To access special features and more reminders, you can upgrade your subscription. Subscription cost: {amount} USD."

if __name__ == "__main__":
    print("Current Configuration Loaded via Pydantic:")
    print(settings.model_dump_json(indent=2))
    print("\nModule-level messages:")
    print(f"MSG_WELCOME: {MSG_WELCOME}")

    print(f"MSG_PAYMENT_PROMPT: {MSG_PAYMENT_PROMPT}")

# Message Constants
MSG_FILTER_DATE_PARSE_ERROR = "Sorry, I couldn't understand the date phrase \"{phrase}\" for filtering. Please try again."
MSG_FILTER_UNSUCCESSFUL = "I couldn't apply the specified filter with the phrase \"{text}\". Please try again or use a different phrase."
MSG_FILTERS_APPLIED = "The following filters were applied: "
MSG_FILTER_NO_CRITERIA_FOUND = "The phrase \"{text}\" didn't contain any recognizable criteria for filtering."
MSG_FILTER_NLU_ERROR = "An error occurred while processing the filter phrase \"{text}\". Please try again."
MSG_LIST_EMPTY_WITH_FILTERS = "No reminders found with the applied filters."
MSG_LIST_HEADER_WITH_FILTERS = "Your reminders (filtered):"
MSG_LIST_EMPTY_NO_REMINDERS: str = (
    "You haven't set any reminders yet. 😕\n"
    "Just send me anything you want me to remind you about via voice or text, and I'll set it up for you. ✨"
)

# General Messages
MSG_ERROR_GENERIC = "Sorry, an error occurred. Please try again or contact support."
MSG_SUCCESS_GENERIC = "Operation completed successfully."
MSG_NOT_IMPLEMENTED_YET = "This feature hasn't been implemented yet. It will be added soon!"
MSG_PAYMENT_BUTTON = "💳 Upgrade to Premium ($9.99)"
MSG_PAYMENT_SUCCESS = "Your payment was successful. Your premium subscription is active until {expiry_date}."
MSG_PAYMENT_SUCCESS_GENERIC = "Your payment was successful and your premium subscription is now active."
MSG_PAYMENT_FAILED = "Sorry, your payment was unsuccessful. Please try again or contact support."
MSG_PAYMENT_CANCELLED = "Payment was cancelled by you."
MSG_PAYMENT_ALREADY_VERIFIED = "This payment has already been verified."
MSG_PAYMENT_PENDING_VERIFICATION = "Your payment status is still unclear. Please wait a moment and check again."
MSG_PAYMENT_VERIFICATION_ERROR = "Payment verification error: {error}. If an amount was deducted from your account, it will be refunded within 72 hours."
MSG_PAYMENT_ERROR = "Error creating payment link. Please try again."
MSG_PAYMENT_CONFIG_ERROR = "Payment configuration error. Please contact the bot administrator."

# Reminder specific messages
MSG_REMINDER_SET = "Your reminder for \"{task}\" has been set for {date} at {time}."
MSG_REMINDER_NOT_FOUND = "Reminder not found."
MSG_REMINDER_DELETED = "Reminder \"{task}\" has been deleted."
MSG_REMINDER_LIMIT_REACHED_FREE = "You have reached the maximum number of allowed reminders ({limit}) for free users. To set more reminders, please upgrade your subscription."
MSG_REMINDER_LIMIT_REACHED_WITH_BUTTON = "You have reached the maximum number of allowed reminders ({limit}) for {tier_name} users. To add more reminders, please upgrade your subscription."
MSG_REMINDER_LIMIT_REACHED_PREMIUM = "You have reached the maximum number of allowed reminders ({limit}) for premium users."
MSG_ALREADY_PREMIUM = "🎉 You already have a premium account! You can create unlimited reminders and enjoy all premium features. Your subscription is active until {expiry_date}." 