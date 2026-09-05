from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_ENV: Literal["development", "testing", "staging", "production"] = "development"
    APP_NAME: str = "AI Business OS"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/ai_business_os"
    TEST_DATABASE_URL: str | None = "postgresql+asyncpg://user:password@localhost:5432/ai_business_os_test"

    LOG_LEVEL: str = "INFO"

    JWT_SECRET: str = "dev_secret_jwt_key_32_characters_long_for_security"
    ENCRYPTION_KEY: str = "dev_encryption_key_32_bytes_long_secret"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_RATE_LIMIT: int = 60

    # Google OAuth Credentials
    GOOGLE_CLIENT_ID: str = "mock_google_client_id.apps.googleusercontent.com"
    GOOGLE_CLIENT_SECRET: str = "mock_google_client_secret"

    # Phase 2 Event Bus & Workflow Configuration
    EVENT_BUS_BACKEND: Literal["in_memory", "redis"] = "in_memory"
    REDIS_URL: str = "redis://localhost:6379/0"
    WORKFLOWS_ENABLED: bool = True
    WORKFLOW_MAX_STEPS: int = 50
    WORKFLOW_MAX_RETRIES: int = 3
    WORKFLOW_TIMEOUT_SECONDS: int = 300


settings = Settings()
