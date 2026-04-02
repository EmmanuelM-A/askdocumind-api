"""
Configuration settings for the DocuChatAPI application.
Each configuration class handles a specific domain of settings.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

from src.logger.logging_utils import LogLevel

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

    ENV: str = Field(default="development", json_schema_extra={"env": "ENV"})
    APP_NAME: str = Field(default="DocuChatAPI")
    PORT: int = Field(default=5000)
    HOST: str = Field(default="127.0.0.1")
    SUPPORTED_VERSIONS: List[str] = Field(default=["1"])
    DEFAULT_VERSION: str = Field(default="1")

    MIN_QUERY_LENGTH: int = Field(
        default=10, json_schema_extra={"env": "MIN_QUERY_LENGTH"}
    )
    MAX_QUERY_LENGTH: int = Field(
        default=2000, json_schema_extra={"env": "MAX_QUERY_LENGTH"}
    )  # TODO: ADD TO ENV
    IS_TRUNCATION_ENABLED: bool = Field(
        default=False, json_schema_extra={"env": "IS_QUERY_TRUNCATION_ENABLED"}
    )  # TODO: ADD TO ENV
    MIN_DOCUMENT_CONTENT_LENGTH: int = Field(
        default=10, json_schema_extra={"env": "MIN_DOCUMENT_CONTENT_LENGTH"}
    )  # TODO: ADD TO ENV
    MAX_DOCUMENT_CONTENT_LENGTH: int = Field(
        default=1000000, json_schema_extra={"env": "MAX_DOCUMENT_CONTENT_LENGTH"}
    )  # TODO: ADD TO ENV

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Database Settings
# ------------------------------------------------------------------
class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    DATABASE_URL: SecretStr = Field(
        default=..., json_schema_extra={"env": "DATABASE_URL"}
    )
    DB_LOG_DIR: str = Field(default=f"{PROJECT_ROOT}/logs/database")
    DB_HOST: str = Field(default="localhost", json_schema_extra={"env": "DB_HOST"})
    DB_PORT: int = Field(default=5432, json_schema_extra={"env": "DB_PORT"})
    DB_NAME: str = Field(default="docu_chat", json_schema_extra={"env": "DB_NAME"})
    DB_USER: str = Field(default="postgres", json_schema_extra={"env": "DB_USER"})
    DB_PASSWORD: SecretStr = Field(default="", json_schema_extra={"env": "DB_PASSWORD"})

    PGADMIN_PORT: int = Field(default=..., json_schema_extra={"env": "PGADMIN_PORT"})

    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT: int = Field(default=30)
    DB_ECHO: bool = Field(default=False)
    DB_IS_POOL_PRE_PING_ENABLED: bool = Field(default=True)

    DB_SAFETY_ENABLED: bool = Field(default=True)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Cache Settings
# ------------------------------------------------------------------
class CacheSettings(BaseSettings):
    """
    Cache configuration settings.
    """

    REDIS_HOST: str = Field(default=..., json_schema_extra={"env": "REDIS_HOST"})
    REDIS_PORT: int = Field(default=6379, json_schema_extra={"env": "REDIS_PORT"})
    REDIS_PASSWORD: SecretStr = Field(
        default="", json_schema_extra={"env": "REDIS_PASSWORD"}
    )
    REDIS_DB: int = Field(default=0, json_schema_extra={"env": "REDIS_DB"})
    REDIS_TTL_SECONDS: int = Field(default=3600)
    REDIS_ENABLED: bool = Field(default=True)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Authentication Settings
# ------------------------------------------------------------------
class AuthSettings(BaseSettings):
    """
    Authentication and authorization configuration settings.
    """

    # ACCESS_SECRET: SecretStr = Field(..., env="ACCESS_TOKEN_SECRET")
    # REFRESH_SECRET: SecretStr = Field(..., env="REFRESH_TOKEN_SECRET")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=5)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    USER_SESSION_SECRET: SecretStr = Field(
        default="dev-anon-session-secret-change-me",
        json_schema_extra={"env": "USER_SESSION_SECRET"},
    )
    ANON_SESSION_COOKIE_NAME: str = Field(default="docu_chat_user_cookie")
    USER_SESSION_TTL_HOURS: int = Field(default=24)
    ANON_SESSION_COOKIE_HTTP_ONLY: bool = Field(default=True)
    ANON_SESSION_COOKIE_SECURE: bool = Field(default=False)
    ANON_SESSION_COOKIE_SAMESITE: str = Field(default="lax")
    ANON_SESSION_COOKIE_DOMAIN: Optional[str] = Field(default=None)
    ANON_SESSION_REFRESH_EVERY_REQUEST: bool = Field(default=True)

    USER_SESSION_CLEANUP_ENABLED: bool = Field(default=True)
    USER_SESSION_CLEANUP_INTERVAL_MINUTES: int = Field(default=60)
    USER_SESSION_CLEANUP_BATCH_SIZE: int = Field(default=100)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# File Processing Settings
# ------------------------------------------------------------------
class FileProcessingSettings(BaseSettings):
    """File processing configuration settings."""

    ALLOWED_FILE_EXTENSIONS: List[str] = Field(default=[".pdf", ".docx", ".txt", ".md"])
    MAX_FILE_SIZE_MB: int = Field(default=20)
    MAX_FILES_PER_UPLOAD: int = Field(default=10)

    LOCAL_FILE_STORAGE_DIR: str = Field(default=f"{PROJECT_ROOT}/data/local/documents")

    MD_FILE_EXT: str = Field(default=".md")
    TXT_FILE_EXT: str = Field(default=".txt")
    PDF_FILE_EXT: str = Field(default=".pdf")
    DOCX_FILE_EXT: str = Field(default=".docx")

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# LLM Integration
# ------------------------------------------------------------------
class LLMIntegrationSettings(BaseSettings):
    """LLM integration configuration settings."""

    # OPENAI_API_KEY: SecretStr = Field(default=..., env="OPENAI_API_KEY")
    LLM_MODEL_NAME: str = Field(default="gpt-3.5-turbo")
    EMBEDDING_MODEL_NAME: str = Field(default="text-embedding-3-small")

    LLM_TEMPERATURE: float = Field(default=0.7)
    MAX_TOKENS: int = Field(default=4096)
    RETRIEVAL_TOP_K: int = Field(
        default=3, json_schema_extra={"env": "RETRIEVAL_TOP_K"}
    )

    OPENAI_API_RATE_LIMIT: int = Field(default=60)
    OPENAI_API_TIMEOUT_SEC: int = Field(default=30)
    MAX_API_RETRIES: int = Field(default=3)
    API_RETRY_DELAY_SEC: int = Field(default=1)

    RESPONSE_PROMPT_FILEPATH: str = Field(
        default=f"{PROJECT_ROOT}/data/prompts/default_response_prompt.yaml"
    )

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Vector Store
# ------------------------------------------------------------------
class VectorStoreSettings(BaseSettings):
    """Vector store configuration settings."""

    DEV_VECTOR_STORE: str = Field(default=f"{PROJECT_ROOT}/data/faiss/indexes")
    DEV_METADATA_STORE: str = Field(default=f"{PROJECT_ROOT}/data/faiss/metadata")

    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=20)

    RETRIEVAL_TOP_K: int = Field(default=3)
    SIMILARITY_THRESHOLD: float = Field(default=0.7)
    MAX_QUERY_LENGTH: int = Field(default=1000)

    MAX_VECTORS_IN_MEMORY: int = Field(default=10000)
    VECTOR_BATCH_SIZE: int = Field(default=100)
    EMBEDDING_CACHE_ENABLED: bool = Field(default=True)
    EMBEDDING_CACHE_DIR: str = Field(default="../data/cache/embeddings")
    MAX_CACHE_SIZE_MB: int = Field(default=500)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Web Search
# ------------------------------------------------------------------
class WebSearchSettings(BaseSettings):
    """Web search configuration settings."""

    IS_WEB_SEARCH_ENABLED: bool = Field(default=False)
    SEARCH_API_KEY: SecretStr = Field(
        default=..., json_schema_extra={"env": "SEARCH_API_KEY"}
    )
    SEARCH_ENGINE_ID: SecretStr = Field(
        default=..., json_schema_extra={"env": "SEARCH_ENGINE_ID"}
    )

    MAX_WEB_SEARCH_RESULTS: int = Field(default=3)
    MAX_WEB_REQUEST_RESULTS: int = Field(default=5)
    WEB_REQUEST_TIMEOUT_SECS: int = Field(default=15)
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

    LOG_LEVEL: str = Field(default=LogLevel.DEBUG)
    LOG_DIRECTORY: str = Field(default=f"{PROJECT_ROOT}/logs")
    LOG_FORMAT: str = Field(
        default="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    # Use a space between date and time for human-friendly logs
    DATE_FORMAT: str = Field(default="%Y-%m-%d %H:%M:%S")
    LOG_MAX_MB: int = Field(default=10)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# API Server
# ------------------------------------------------------------------
class APIServerSettings(BaseSettings):
    """API server configuration settings."""

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    WORKERS: int = Field(default=1)

    DOCS_URL: str = Field(default="/docs")
    REDOC_URL: str = Field(default="/redoc")

    API_V1_PREFIX: str = Field(default="/api/v1")
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000"])
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: List[str] = Field(default=["*"])
    CORS_ALLOW_HEADERS: List[str] = Field(default=["*"])

    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW: int = Field(default=60)

    MAX_CHATS_PER_USER: int = Field(default=1)
    MAX_DOCUMENTS_PER_CHAT: int = Field(default=5)
    MAX_CHAT_QUERIES_PER_MINUTE: int = Field(default=10)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Monitoring
# ------------------------------------------------------------------
class MonitoringSettings(BaseSettings):
    """Monitoring and metrics configuration settings."""

    ENABLE_METRICS: bool = Field(default=True)
    METRICS_ENDPOINT: str = Field(default="/metrics")

    # SENTRY_DSN: Optional[SecretStr] = Field(default=None, env="SENTRY_DSN")
    SENTRY_ENVIRONMENT: str = Field(default="development")

    QA_SQLITE_DB_PATH: str = Field(default="../data/db/qa_log.db")
    ENABLE_EVALUATION_LOGGING: bool = Field(default=False)

    HEALTH_CHECK_TIMEOUT: int = Field(default=30)

    model_config = _DEFAULT_MODEL_CONFIG


# ------------------------------------------------------------------
# Main Settings Container
# ------------------------------------------------------------------
class Settings(BaseSettings):
    """Main settings container aggregating all configuration domains."""

    app: CoreAppSettings = CoreAppSettings()
    database: DatabaseSettings = DatabaseSettings()
    cache: CacheSettings = CacheSettings()
    auth: AuthSettings = AuthSettings()
    files: FileProcessingSettings = FileProcessingSettings()
    llm: LLMIntegrationSettings = LLMIntegrationSettings()
    vector: VectorStoreSettings = VectorStoreSettings()
    web: WebSearchSettings = WebSearchSettings()
    logging: LoggingSettings = LoggingSettings()
    server: APIServerSettings = APIServerSettings()
    monitoring: MonitoringSettings = MonitoringSettings()

    model_config = _DEFAULT_MODEL_CONFIG


# Global settings instance
settings = Settings()
