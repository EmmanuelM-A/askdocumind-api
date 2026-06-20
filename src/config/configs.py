"""
Configuration settings for the AskDocuMind API application.
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
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

_DEFAULT_MODEL_CONFIG = SettingsConfigDict(
    env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
)


class _BaseSettings(BaseSettings):
    """Shared base: treats empty-string env vars as unset, falling back to field defaults."""

    @model_validator(mode="before")
    @classmethod
    def _drop_empty_strings(cls, values: dict) -> dict:
        return {k: v for k, v in values.items() if v != ""}


# ------------------------------------------------------------------
# Core Settings
# ------------------------------------------------------------------
class CoreAppSettings(_BaseSettings):
    """Core application configuration settings."""

    ENV: str = Field(default=...)
    PORT: int = Field(default=...)
    HOST: str = Field(default="0.0.0.0")

    # Internal API routing constants
    DEFAULT_VERSION: str = Field(default="1")

    # Business-logic thresholds
    MIN_QUERY_LENGTH: int = Field(default=10)
    MAX_QUERY_LENGTH: int = Field(default=2000)
    IS_QUERY_TRUNCATION_ENABLED: bool = Field(default=False)
    MIN_DOCUMENT_CONTENT_LENGTH: int = Field(default=10)
    MAX_DOCUMENT_CONTENT_LENGTH: int = Field(default=1000000)

    MAX_CHATS_PER_USER: int = Field(default=1)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Database Settings
# ------------------------------------------------------------------
class DatabaseSettings(_BaseSettings):
    """Database configuration settings."""

    DATABASE_URL: SecretStr = Field(default=...)

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
    DB_ECHO: bool = Field(default=False)
    DB_IS_POOL_PRE_PING_ENABLED: bool = Field(default=True)
    DB_SAFETY_ENABLED: bool = Field(default=True)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Authentication Settings
# ------------------------------------------------------------------
class AuthSettings(_BaseSettings):
    """Authentication and authorization configuration settings."""

    USER_SESSION_SECRET: SecretStr = Field(default=...)
    COOKIE_NAME: str = Field(default="askdocumind_user_cookie")
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
class AnonymousUserSessionSettings(_BaseSettings):
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
class FileProcessingSettings(_BaseSettings):
    """File processing configuration settings."""

    ALLOWED_FILE_EXTENSIONS: List[str] = Field(default=[".pdf", ".docx", ".txt", ".md"])
    MAX_FILE_SIZE_MB: float = Field(default=0.5)  # Max size per file
    MAX_FILES_PER_CHAT_MB: int = Field(
        default=1
    )  # Max total size of all files per chat
    MAX_DOCUMENTS_PER_CHAT: int = Field(default=10)

    LOCAL_FILE_STORAGE_DIR: str = Field(default=f"{_PROJECT_ROOT}/data/local/documents")

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# LLM Integration
# ------------------------------------------------------------------
class LLMIntegrationSettings(_BaseSettings):
    """LLM integration configuration settings."""

    LLM_MODEL_NAME: str = Field(default=..., validation_alias="OPENAI_LLM_MODEL_NAME")
    EMBEDDING_MODEL_NAME: str = Field(
        default=..., validation_alias="OPENAI_EMBEDDING_MODEL_NAME"
    )
    LLM_TEMPERATURE: float = Field(default=0.7)
    LLM_REQUEST_TIMEOUT_SECS: int = Field(default=30)
    LLM_MAX_RETRIES: int = Field(default=2)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=1024)

    RESPONSE_PROMPT_FILEPATH: str = Field(
        default=f"{_PROJECT_ROOT}/data/prompts/default_response_prompt.yaml"
    )

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Vector Store
# ------------------------------------------------------------------
class VectorStoreSettings(_BaseSettings):
    """Vector store configuration settings."""

    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=60)
    RETRIEVAL_TOP_K: int = Field(default=3)
    SIMILARITY_THRESHOLD: float = Field(default=0.4)
    MAX_VECTORS_IN_MEMORY: int = Field(default=10000)
    VECTOR_BATCH_SIZE: int = Field(default=100)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Web Search
# ------------------------------------------------------------------
class WebSearchSettings(_BaseSettings):
    """Web search configuration settings."""

    IS_WEB_SEARCH_ENABLED: bool = Field(default=False)
    SEARCH_API_KEY: SecretStr = Field(default=...)
    SEARCH_ENGINE_ID: SecretStr = Field(default=...)

    MAX_WEB_SEARCH_RESULTS: int = Field(default=3)
    WEB_REQUEST_TIMEOUT_SECS: int = Field(default=15)
    WEB_REQUEST_DELAY_SECS: int = Field(default=1)
    WEB_SEARCH_FALLBACK_ENABLED: bool = Field(default=True)

    WEB_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
class LoggingSettings(_BaseSettings):
    """Logging configuration settings."""

    LOG_LEVEL: str = Field(default="DEBUG")
    LOG_TO: Literal["CONSOLE", "FILE", "BOTH"] = Field(default="FILE")
    LOG_DIRECTORY: str = Field(default=f"{_PROJECT_ROOT}/logs")
    LOG_FORMAT: str = Field(
        default="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    LOG_AS_JSON: bool = Field(default=False)
    DATE_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S")
    LOG_MAX_MB: int = Field(default=10)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# API Server
# ------------------------------------------------------------------
class APIServerSettings(_BaseSettings):
    """API server configuration settings."""

    WORKERS: int = Field(default=1)

    CORS_ORIGINS: List[str] = Field(default=...)
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: List[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        default=["Content-Type", "Accept-Version", "Authorization", "X-Requested-With"]
    )

    MAX_REQUEST_BODY_SIZE_MB: float = Field(default=10.0)

    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW: int = Field(default=60)

    MAX_CHAT_QUERIES_PER_MINUTE: int = Field(default=10)
    MAX_UPLOAD_REQUESTS_PER_MINUTE: int = Field(default=5)
    MAX_SESSION_REQUESTS_PER_MINUTE: int = Field(default=10)
    MAX_CONCURRENT_REQUESTS: int = Field(default=50)

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
