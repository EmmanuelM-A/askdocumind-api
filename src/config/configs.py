"""
Configuration settings for the DocuChatAPI application.
Each configuration class handles a specific domain of settings.
"""

from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# ------------------------------------------------------------------
# Environment Setup
# ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

_DEFAULT_MODEL_CONFIG = SettingsConfigDict(
    env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
)


# ------------------------------------------------------------------
# Core Settings
# ------------------------------------------------------------------
class CoreAppSettings(BaseSettings):
    """Core application configuration settings."""

    ENV: str = Field(default=..., validation_alias="ENV")
    PORT: int = Field(default=..., validation_alias="PORT")
    HOST: str = Field(default="0.0.0.0", validation_alias="HOST")

    # Internal API routing constants
    DEFAULT_VERSION: str = Field(default="1")

    # Business-logic thresholds
    MIN_QUERY_LENGTH: int = Field(default=10, validation_alias="MIN_QUERY_LENGTH")
    MAX_QUERY_LENGTH: int = Field(default=2000, validation_alias="MAX_QUERY_LENGTH")
    IS_QUERY_TRUNCATION_ENABLED: bool = Field(default=False, validation_alias="IS_QUERY_TRUNCATION_ENABLED")
    MIN_DOCUMENT_CONTENT_LENGTH: int = Field(
        default=10, validation_alias="MIN_DOCUMENT_CONTENT_LENGTH"
    )
    MAX_DOCUMENT_CONTENT_LENGTH: int = Field(
        default=1000000, validation_alias="MAX_DOCUMENT_CONTENT_LENGTH"
    )

    MAX_CHATS_PER_USER: int = Field(default=1, validation_alias="MAX_CHATS_PER_USER")

    @model_validator(mode="before")
    @classmethod
    def _drop_empty_strings(cls, values: dict) -> dict:
        return {k: v for k, v in values.items() if v != ""}

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Database Settings
# ------------------------------------------------------------------
class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    DATABASE_URL: SecretStr = Field(default=..., validation_alias="DATABASE_URL")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _ensure_asyncpg_driver(cls, v: str) -> str:
        url = v if isinstance(v, str) else str(v)
        for sync_prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if url.startswith(sync_prefix):
                return "postgresql+asyncpg://" + url[len(sync_prefix) :]
        return url

    # Pool tuning
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT_SECS: int = Field(default=30)
    DB_ECHO: bool = Field(default=False, validation_alias="DB_ECHO")
    DB_IS_POOL_PRE_PING_ENABLED: bool = Field(default=True)
    DB_SAFETY_ENABLED: bool = Field(default=True)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Authentication Settings
# ------------------------------------------------------------------
class AuthSettings(BaseSettings):
    """Authentication and authorization configuration settings."""

    USER_SESSION_SECRET: SecretStr = Field(
        default=..., validation_alias="USER_SESSION_SECRET"
    )
    COOKIE_NAME: str = Field(default="docu_chat_user_cookie")
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = Field(
        default="none", validation_alias="ANON_SESSION_COOKIE_SAMESITE"
    )
    COOKIE_DOMAIN: Optional[str] = Field(
        default=None, validation_alias="ANON_SESSION_COOKIE_DOMAIN"
    )

    @field_validator("COOKIE_DOMAIN", mode="before")
    @classmethod
    def _coerce_none_string(cls, v: object) -> object:
        if isinstance(v, str) and v.strip().lower() == "none":
            return None
        return v

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Anonymous User Session Settings
# ------------------------------------------------------------------
class AnonymousUserSessionSettings(BaseSettings):
    """Settings related to anonymous user session management."""

    CLEANUP_ENABLED: bool = Field(default=..., validation_alias="USER_CLEANUP_ENABLED")
    BATCH_SIZE: int = Field(default=100, validation_alias="USER_CLEANUP_BATCH_SIZE")
    CLEANUP_INTERVAL_H: int = Field(
        default=1, validation_alias="USER_CLEANUP_INTERVAL_HOURS"
    )
    TTL_HOURS: int = Field(default=60, validation_alias="USER_TTL_HOURS")

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# File Processing Settings
# ------------------------------------------------------------------
class FileProcessingSettings(BaseSettings):
    """File processing configuration settings."""

    ALLOWED_FILE_EXTENSIONS: List[str] = Field(default=[".pdf", ".docx", ".txt", ".md"])
    MAX_FILE_SIZE_MB: float = Field(
        default=0.5, validation_alias="MAX_FILE_SIZE_MB"
    )  # Max size per file
    MAX_FILES_PER_CHAT_MB: int = Field(
        default=1, validation_alias="MAX_FILES_PER_CHAT_MB"
    )  # Max total size of all files per chat

    LOCAL_FILE_STORAGE_DIR: str = Field(default=f"{PROJECT_ROOT}/data/local/documents")

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# LLM Integration
# ------------------------------------------------------------------
class LLMIntegrationSettings(BaseSettings):
    """LLM integration configuration settings."""

    LLM_MODEL_NAME: str = Field(default=..., validation_alias="LLM_MODEL_NAME")
    EMBEDDING_MODEL_NAME: str = Field(
        default=..., validation_alias="EMBEDDING_MODEL_NAME"
    )
    LLM_TEMPERATURE: float = Field(default=0.7, validation_alias="LLM_TEMPERATURE")

    RESPONSE_PROMPT_FILEPATH: str = Field(
        default=f"{PROJECT_ROOT}/data/prompts/default_response_prompt.yaml"
    )

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Vector Store
# ------------------------------------------------------------------
class VectorStoreSettings(BaseSettings):
    """Vector store configuration settings."""

    CHUNK_SIZE: int = Field(default=1000, validation_alias="CHUNK_SIZE")
    CHUNK_OVERLAP: int = Field(default=60, validation_alias="CHUNK_OVERLAP")
    RETRIEVAL_TOP_K: int = Field(default=3, validation_alias="RETRIEVAL_TOP_K")
    SIMILARITY_THRESHOLD: float = Field(
        default=0.4, validation_alias="SIMILARITY_THRESHOLD"
    )
    MAX_VECTORS_IN_MEMORY: int = Field(default=10000)
    VECTOR_BATCH_SIZE: int = Field(default=100)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Web Search
# ------------------------------------------------------------------
class WebSearchSettings(BaseSettings):
    """Web search configuration settings."""

    IS_WEB_SEARCH_ENABLED: bool = Field(
        default=False, validation_alias="IS_WEB_SEARCH_ENABLED"
    )
    SEARCH_API_KEY: SecretStr = Field(default=..., validation_alias="SEARCH_API_KEY")
    SEARCH_ENGINE_ID: SecretStr = Field(
        default=..., validation_alias="SEARCH_ENGINE_ID"
    )

    MAX_WEB_SEARCH_RESULTS: int = Field(default=3, validation_alias="MAX_WEB_SEARCH_RESULTS")
    MAX_WEB_REQUEST_RESULTS: int = Field(default=5)
    WEB_REQUEST_TIMEOUT_SECS: int = Field(default=15, validation_alias="WEB_REQUEST_TIMEOUT_SECS")
    WEB_REQUEST_DELAY_SECS: int = Field(default=1)
    WEB_SEARCH_FALLBACK_ENABLED: bool = Field(default=True)

    WEB_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )

    MAX_WEB_CONTENT_LENGTH: int = Field(default=10000)
    MIN_WEB_CONTENT_LENGTH: int = Field(default=100)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    LOG_LEVEL: str = Field(default="DEBUG", validation_alias="LOG_LEVEL")
    LOG_TO: Literal["CONSOLE", "FILE", "BOTH"] = Field(
        default="FILE", validation_alias="LOG_TO"
    )
    LOG_DIRECTORY: str = Field(default=f"{PROJECT_ROOT}/logs")
    LOG_FORMAT: str = Field(
        default="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    LOG_AS_JSON: bool = Field(default=False, validation_alias="LOG_AS_JSON")
    DATE_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S")
    LOG_MAX_MB: int = Field(default=10)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# API Server
# ------------------------------------------------------------------
class APIServerSettings(BaseSettings):
    """API server configuration settings."""

    WORKERS: int = Field(default=1)

    CORS_ORIGINS: List[str] = Field(
        default=...,
        validation_alias="CORS_ORIGINS",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        default=["Content-Type", "Accept-Version", "Authorization", "X-Requested-With"]
    )

    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW: int = Field(default=60)

    MAX_CHAT_QUERIES_PER_MINUTE: int = Field(default=10)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Main Settings Container
# ------------------------------------------------------------------
class Settings(BaseSettings):
    """Main settings container aggregating all configuration domains."""

    app: CoreAppSettings = CoreAppSettings()
    database: DatabaseSettings = DatabaseSettings()
    auth: AuthSettings = AuthSettings()
    anon: AnonymousUserSessionSettings = AnonymousUserSessionSettings()
    files: FileProcessingSettings = FileProcessingSettings()
    llm: LLMIntegrationSettings = LLMIntegrationSettings()
    vector: VectorStoreSettings = VectorStoreSettings()
    web: WebSearchSettings = WebSearchSettings()
    logging: LoggingSettings = LoggingSettings()
    server: APIServerSettings = APIServerSettings()

    model_config = _DEFAULT_MODEL_CONFIG


# Global settings instance
settings = Settings()
