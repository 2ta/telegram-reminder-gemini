import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram API Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./default.db") # Default to a local SQLite DB

# Google Cloud / Gemini Configuration
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GEMINI_PROJECT_ID = os.getenv("GEMINI_PROJECT_ID")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.0-pro-001") # Default model

# Payment Gateway (Zibal) Configuration - If needed later
ZIBAL_MERCHANT_KEY = os.getenv("ZIBAL_MERCHANT_KEY")
PAYMENT_CALLBACK_URL_BASE = os.getenv("PAYMENT_CALLBACK_URL_BASE") # e.g., https://yourdomain.com/bot

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/bot.log")
LOG_FILE_MAX_BYTES = int(os.getenv("LOG_FILE_MAX_BYTES", 1024 * 1024 * 5)) # 5MB
LOG_FILE_BACKUP_COUNT = int(os.getenv("LOG_FILE_BACKUP_COUNT", 3))

# Other application settings
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "fa")

# Placeholder for different environments if needed later
# Example:
# ENV = os.getenv("ENV", "development")
# if ENV == "production":
#     DATABASE_URL = os.getenv("PROD_DATABASE_URL")
#     # other production specific settings
# elif ENV == "testing":
#     DATABASE_URL = "sqlite:///./test.db"
#     # other testing specific settings


def validate_config():
    """Validates that essential configuration variables are set."""
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        # Add other critical variables here as the project grows
        # e.g., "DATABASE_URL" if not using default,
        # "GOOGLE_APPLICATION_CREDENTIALS", "GEMINI_PROJECT_ID", "GEMINI_LOCATION"
        # if core NLU features are critical for startup.
    ]
    missing_vars = [var for var in required_vars if not globals().get(var)]
    if missing_vars:
        raise ValueError(f"Missing critical environment variables: {', '.join(missing_vars)}")

# Automatically validate when this module is imported
# You might want to call this explicitly at app startup instead
# validate_config() 
# For now, let's not auto-validate to allow flexibility during development.

if __name__ == "__main__":
    # Print current config for debugging (be careful with sensitive data)
    print("Current Configuration:")
    print(f"TELEGRAM_BOT_TOKEN: {'*' * 5 if TELEGRAM_BOT_TOKEN else None}")
    print(f"DATABASE_URL: {DATABASE_URL}")
    print(f"GOOGLE_APPLICATION_CREDENTIALS: {GOOGLE_APPLICATION_CREDENTIALS}")
    print(f"LOG_LEVEL: {LOG_LEVEL}") 