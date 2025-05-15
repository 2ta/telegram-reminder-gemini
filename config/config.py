import os
from typing import Optional, Union, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, AnyHttpUrl, AliasChoices

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
    GEMINI_API_KEY: Optional[str] = Field(default=None, validation_alias=AliasChoices('GOOGLE_API_KEY', 'GEMINI_API_KEY'))

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

    # Environment setting (dev, test, prod)
    APP_ENV: Literal["development", "testing", "production"] = "development"

settings = Settings()

if __name__ == "__main__":
    print("Current Configuration Loaded via Pydantic:")
    print(settings.model_dump_json(indent=2)) 