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


settings = Settings()
