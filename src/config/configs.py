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


class _ServerSettings(_BaseSettings):
    """
    Server configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development"
    )
    PORT: int = Field(default=5001, ge=1, le=65535)
    CORS_ORIGINS: list[str] = Field(default=...)

    MAX_REQUEST_BODY_SIZE_MB: float = Field(default=10.0, gt=0, le=500)
    RATE_LIMIT_REQUESTS: int = Field(default=100, ge=1, le=10000)
    RATE_LIMIT_WINDOW_SECS: int = Field(default=60, ge=1, le=3600)


class _LoggingSettings(_BaseSettings):
    """
    Logging configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="DEBUG"
    )
    LOG_FORMAT: str = Field(
        default="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s"
    )
    DATE_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S")


class _DatabaseSettings(_BaseSettings):
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


class _AuthSettings(_BaseSettings):
    """
    Authentication configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    COOKIE_DOMAIN: str = Field(default="localhost")
    COOKIE_TTL_HOURS: int = Field(default=12, ge=1, le=168)

    # Anonymous user session settings
    ANONYMOUS_TOKEN_SECRET: SecretStr = Field(default=...)
    ANONYMOUS_TOKEN_TTL_DAYS: int = Field(default=7, ge=1, le=30)
    ANONYMOUS_COOKIE_NAME: str = Field(default="anonymous_session")
    UPDATE_LAST_SEEN_FREQ_MINS: int = Field(default=5, ge=1, le=60)


class _ChatSessionSettings(_BaseSettings):
    """
    Chat session configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    MAX_QUERIES_PER_MINUTE: int = Field(default=60, ge=1, le=1000)


class _UploadSettings(_BaseSettings):
    """
    Upload configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # Object storage (Both S3 and MinIO compatible)
    S3_ENDPOINT_URL: SecretStr = Field(default=...)
    S3_ACCESS_KEY_ID: SecretStr = Field(default=...)
    S3_SECRET_ACCESS_KEY: SecretStr = Field(default=...)
    S3_REGION: SecretStr = Field(default=...)
    S3_BUCKET_NAME: SecretStr = Field(default=...)

    # Business rules
    MAX_DOCS_PER_SESSION: int = Field(default=10, ge=1, le=100)
    ALLOWED_FILE_EXTENSIONS: list[str] = Field(default=...)
    ALLOWED_CODE_EXTENSIONS: list[str] = Field(default=...)
    ALLOWED_CONTENT_TYPES: list[str] = Field(default=...)
    PROCESSING_TIMEOUT_SECS: int = Field(default=30, ge=1, le=300)
    BLOCK_SIZE_TO_READ_BYTES: int = Field(default=8192, ge=1024, le=65536)
    MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=500)


class _RAGSettings(_BaseSettings):
    """
    Retrieval-Augmented Generation (RAG) configuration settings for the
    AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # Embeddings
    EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=1, le=10000)
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")
    EMBEDDING_REQUEST_TIMEOUT_SECS: int = Field(default=30, ge=1, le=300)
    EMBEDDING_MAX_RETRIES: int = Field(default=3, ge=0, le=10)

    # Chunkers
    STREAM_FLUSH_CHARS: int = Field(default=20000, ge=7500, le=40000)
    PROCESSING_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    MIN_CONTENT_LENGTH: int = Field(default=150, ge=100, le=1000)

    # Extraction
    READ_BLOCK_BYTES: int = Field(default=8192, ge=1024, le=65536)
    FALLBACK_ENCODING: str = Field(default="cp1252")
    SEGMENT_TARGET_CHARS: int = Field(default=1000, ge=100, le=10000)

    # Reranking

    # Web Search
    MAX_SEARCH_RESULTS: int = Field(default=10, le=30, ge=5)
    USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64)", min_length=10
    )
    BRAVE_API_KEY: SecretStr = Field(default=...)

    # Retrieval
    MIN_CHUNKS_NEEDED_FOR_WEB_SEARCH: int = Field(default=25, ge=20, le=100)
    MIN_CHUNKS_NEEDED_FOR_RERANKING: int = Field(default=55, ge=50, le=100)

    @field_validator("BRAVE_API_KEY")
    @classmethod
    def validate_brave_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("BRAVE_API_KEY cannot be empty.")
        return value


class _LLMSettings(_BaseSettings):
    """
    Large Language Model (LLM) configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    MODEL_NAME: str = Field(default="gpt-4o-mini", alias="LLM_MODEL_NAME")
    TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    REQUEST_TIMEOUT_SECS: int = Field(
        default=30, ge=1, le=300, alias="LLM_REQUEST_TIMEOUT_SECS"
    )
    MAX_RETRIES: int = Field(default=3, ge=0, le=10, alias="LLM_MAX_RETRIES")
    MAX_OUTPUT_TOKENS: int = Field(default=1024, ge=1, le=16000)


# ------------------------------------------------------------------
# Main Settings Container
# ------------------------------------------------------------------
class _Settings(BaseSettings):
    """
    Main settings container aggregating all configuration domains.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    server: _ServerSettings = _ServerSettings()
    logging: _LoggingSettings = _LoggingSettings()
    database: _DatabaseSettings = _DatabaseSettings()
    auth: _AuthSettings = _AuthSettings()
    chat: _ChatSessionSettings = _ChatSessionSettings()
    uploads: _UploadSettings = _UploadSettings()
    rag: _RAGSettings = _RAGSettings()
    llm: _LLMSettings = _LLMSettings()


# Global settings instance
settings = _Settings()
