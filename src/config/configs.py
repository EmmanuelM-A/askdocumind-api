"""
Configuration settings for the AskDocuMind API application.
Each configuration class handles a specific domain of settings.
"""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, model_validator, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

_DEFAULT_MODEL_CONFIG = SettingsConfigDict(
    env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
)


class _BaseSettings(BaseSettings):
    """
    Shared base settings class for all settings classes in the application.
    """

    @model_validator(mode="before")
    @classmethod
    def _drop_empty_strings(cls, values: dict) -> dict:
        return {k: v for k, v in values.items() if v != ""}


class ServerSettings(_BaseSettings):
    """
    Server configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development"
    )
    PORT: int = Field(default=8001, ge=1, le=65535)


class LoggingSettings(_BaseSettings):
    """
    Logging configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    LOG_DIRECTORY: str = Field(default=f"{_PROJECT_ROOT}/logs")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="DEBUG"
    )
    LOG_FORMAT: str = Field(
        default="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s"
    )
    DATE_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S")


class DatabaseSettings(_BaseSettings):
    """
    Database configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    DATABASE_URL: SecretStr = Field(default=...)

    # Pool tuning
    DB_ECHO: bool = Field(default=False)
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=200)
    DB_POOL_TIMEOUT_SECS: int = Field(default=30, ge=1, le=300)
    DB_IS_POOL_PRE_PING_ENABLED: bool = Field(default=True)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value().strip()
        if not url:
            raise ValueError("DATABASE_URL cannot be empty.")
        if "//" not in url:
            raise ValueError("DATABASE_URL must be a valid connection string.")
        return value


class AuthSettings(_BaseSettings):
    """
    Authentication configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    ANONYMOUS_TOKEN_SECRET: SecretStr = Field(default=...)
    ANONYMOUS_TOKEN_TTL_DAYS: int = Field(default=7, ge=1, le=30)


# ------------------------------------------------------------------
# Main Settings Container
# ------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Main settings container aggregating all configuration domains.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    server: ServerSettings = ServerSettings()
    logging: LoggingSettings = LoggingSettings()
    database: DatabaseSettings = DatabaseSettings()
    auth: AuthSettings = AuthSettings()


# Global settings instance
settings = Settings()
