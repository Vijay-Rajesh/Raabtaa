from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "SafeReach"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/Raabta"

    # JWT
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Gemini (used as the LLM backing the OpenAI Agents SDK, via Gemini's
    # OpenAI-compatible endpoint -- see app/agents/model_provider.py)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # WhatsApp Cloud API
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v20.0"
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_MOCK_MODE: bool = True

    # Telegram Bot API fallback
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_API_BASE_URL: str = "https://api.telegram.org"
    TELEGRAM_MOCK_MODE: bool = True

    # Geofence defaults
    MIN_RADIUS_METERS: int = 50
    MAX_RADIUS_METERS: int = 1000

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
