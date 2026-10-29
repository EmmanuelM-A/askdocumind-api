"""
Configuration settings for the AskDocuMind API application.
Each configuration class handles a specific domain of settings.
"""

import codecs
from pathlib import Path
from typing import Literal, Self

from dotenv import load_dotenv
from limits import parse_many
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

_DEFAULT_MODEL_CONFIG = SettingsConfigDict(
    env_file=_ENV_FILE,
    env_file_encoding="utf-8",
    env_ignore_empty=True,
    extra="ignore",
)

# Native output size of the OpenAI embedding models. The embedder does not
# request a reduced size, so EMBEDDING_DIMENSIONS must match.
_EMBEDDING_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def _require_secret(name: str, value: SecretStr, min_length: int = 1) -> SecretStr:
    if len(value.get_secret_value().strip()) < min_length:
        raise ValueError(f"{name} must be at least {min_length} characters.")
    return value


def _require_file(name: str, value: str) -> str:
    if not Path(value).is_file():
        raise ValueError(f"{name} file not found: {value}")
    return value


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
    # 0.0.0.0 is needed inside a container, so the port can be reached from outside
    HOST: str = Field(default="127.0.0.1", min_length=1)
    PORT: int = Field(default=5001, ge=1, le=65535)
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"], min_length=1)
    MAX_CONCURRENCY: int = Field(
        default=50, ge=1, le=500, validation_alias="SERVER_MAX_CONCURRENCY"
    )

    MAX_REQUEST_BODY_SIZE_MB: float = Field(default=11.0, gt=0, le=60)
    MAX_CONCURRENT_REQUESTS: int = Field(default=10, ge=1, le=100)
    RATE_LIMIT_REQUESTS: int = Field(default=100, ge=1, le=1000)
    RATE_LIMIT_WINDOW_SECS: int = Field(default=60, ge=1, le=3600)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_STORAGE_URI: str = Field(default="memory://")

    # Per route group limits, in the limits notation (e.g. "10/minute")
    RATE_LIMIT_HEALTH_SERVER: str = Field(default="60/minute")
    RATE_LIMIT_HEALTH_DB: str = Field(default="30/minute")
    RATE_LIMIT_CHAT_SESSION: str = Field(default="10/minute")
    RATE_LIMIT_UPLOADS: str = Field(default="5/minute")
    RATE_LIMIT_CHATBOT: str = Field(default="10/minute")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in value]
        for origin in origins:
            # Credentials are allowed, so a wildcard would let any site make
            # requests with the user's cookie
            if origin == "*":
                raise ValueError("CORS_ORIGINS cannot contain '*'.")
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin must start with http(s)://: {origin}")
        return origins

    @field_validator(
        "RATE_LIMIT_HEALTH_SERVER",
        "RATE_LIMIT_HEALTH_DB",
        "RATE_LIMIT_CHAT_SESSION",
        "RATE_LIMIT_UPLOADS",
        "RATE_LIMIT_CHATBOT",
    )
    @classmethod
    def validate_rate_limit(cls, value: str) -> str:
        parse_many(value)
        return value

    @model_validator(mode="after")
    def validate_concurrency(self) -> Self:
        if self.MAX_CONCURRENCY < self.MAX_CONCURRENT_REQUESTS:
            raise ValueError(
                "SERVER_MAX_CONCURRENCY must be at least MAX_CONCURRENT_REQUESTS."
            )
        return self


class _LoggingSettings(_BaseSettings):
    """
    Logging configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
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
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=50)
    DB_POOL_TIMEOUT_SECS: int = Field(default=30, ge=1, le=300)
    DB_IS_POOL_PRE_PING_ENABLED: bool = Field(default=True)

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value().strip()
        if not url:
            raise ValueError("DATABASE_URL cannot be empty.")
        # The engine is async, so the URL must name an async Postgres driver
        if not url.startswith(("postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError(
                "DATABASE_URL must start with postgresql+asyncpg:// "
                "or postgresql+psycopg://."
            )
        return value


class _AuthSettings(_BaseSettings):
    """
    Authentication configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # None sets a host-only cookie, which also works on localhost
    COOKIE_DOMAIN: str | None = Field(default=None)

    # Anonymous user session settings
    ANONYMOUS_TOKEN_SECRET: SecretStr = Field(default=...)
    ANONYMOUS_TOKEN_TTL_HOURS: int = Field(default=1, ge=1, le=5)
    ANONYMOUS_COOKIE_NAME: str = Field(
        default="anonymous_session", pattern=r"^[A-Za-z0-9_-]+$"
    )
    UPDATE_LAST_SEEN_FREQ_MINS: int = Field(default=5, ge=1, le=60)

    @field_validator("ANONYMOUS_TOKEN_SECRET")
    @classmethod
    def validate_token_secret(cls, value: SecretStr) -> SecretStr:
        # HS256 needs a key of at least 256 bits
        return _require_secret("ANONYMOUS_TOKEN_SECRET", value, min_length=32)


class _ChatSessionSettings(_BaseSettings):
    """
    Chat session configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    MAX_CHATS_PER_USER: int = Field(default=5, ge=1, le=100)


class _UploadSettings(_BaseSettings):
    """
    Upload configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # Object storage (Both S3 and MinIO compatible). Leave the endpoint unset
    # to use AWS S3.
    S3_ENDPOINT_URL: str | None = Field(default=None)
    S3_ACCESS_KEY_ID: SecretStr = Field(default=...)
    S3_SECRET_ACCESS_KEY: SecretStr = Field(default=...)
    S3_REGION: str = Field(default="us-east-1", min_length=1)
    S3_BUCKET_NAME: str = Field(
        default=..., pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
    )

    # Business rules
    MAX_DOCS_PER_SESSION: int = Field(default=10, ge=1, le=100)
    ALLOWED_FILE_EXTENSIONS: list[str] = Field(
        default=[".pdf", ".docx", ".txt", ".md", ".html"]
    )
    ALLOWED_CODE_EXTENSIONS: list[str] = Field(
        default=[".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"]
    )
    ALLOWED_CONTENT_TYPES: list[str] = Field(
        default=[
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
            "text/html",
            "text/x-python",
            "text/javascript",
            "application/javascript",
            "text/x-java-source",
        ]
    )
    MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=50)
    MAX_CONCURRENT_UPLOADS: int = Field(default=5, ge=1, le=20)

    @field_validator("S3_ENDPOINT_URL")
    @classmethod
    def validate_s3_endpoint_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("S3_ENDPOINT_URL must start with http(s)://.")
        return value

    @field_validator("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
    @classmethod
    def validate_s3_credentials(cls, value: SecretStr, info) -> SecretStr:
        return _require_secret(info.field_name, value)

    @field_validator("ALLOWED_FILE_EXTENSIONS", "ALLOWED_CODE_EXTENSIONS")
    @classmethod
    def validate_extensions(cls, value: list[str]) -> list[str]:
        extensions = [ext.strip().lower() for ext in value if ext.strip()]
        for ext in extensions:
            if not ext.startswith(".") or len(ext) < 2:
                raise ValueError(f"File extension must look like '.pdf': {ext}")
        return extensions

    @field_validator("ALLOWED_CONTENT_TYPES")
    @classmethod
    def validate_content_types(cls, value: list[str]) -> list[str]:
        content_types = [ct.strip().lower() for ct in value if ct.strip()]
        for content_type in content_types:
            if content_type.count("/") != 1:
                raise ValueError(
                    f"Content type must look like 'type/subtype': {content_type}"
                )
        return content_types


class _RAGSettings(_BaseSettings):
    """
    Retrieval-Augmented Generation (RAG) configuration settings for the
    AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # Embeddings. Changing the dimensions needs a migration of the vector column.
    EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=1, le=3072)
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")
    EMBEDDING_REQUEST_TIMEOUT_SECS: int = Field(default=30, ge=1, le=300)
    EMBEDDING_MAX_RETRIES: int = Field(default=3, ge=0, le=10)

    # Chunkers
    STREAM_FLUSH_CHARS: int = Field(default=20000, ge=7500, le=40000)
    PROCESSING_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    MIN_CONTENT_LENGTH: int = Field(default=150, ge=100, le=1000)

    # Extraction, also used to read uploaded files
    READ_BLOCK_BYTES: int = Field(default=8192, ge=1024, le=65536)
    FALLBACK_ENCODING: str = Field(default="cp1252")
    SEGMENT_TARGET_CHARS: int = Field(default=1000, ge=100, le=10000)

    # Expansion
    EXPANSION_PROMPT_TEMPLATE: str = Field(
        default=f"{_PROJECT_ROOT}/src/prompts/expand_query_prompt.yaml"
    )

    # Reranking
    RERANKER_MODEL_NAME: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    RERANKER_MAX_LENGTH: int = Field(default=256, ge=50, le=512)
    RERANKER_BATCH_SIZE: int = Field(default=32, ge=1, le=128)

    # Retrieval
    MIN_CHUNKS_NEEDED_FOR_WEB_SEARCH: int = Field(default=3, ge=1, le=100)
    MIN_CHUNKS_NEEDED_FOR_RERANKING: int = Field(default=2, ge=2, le=100)
    MAX_RETRIEVAL_CANDIDATES: int = Field(default=50, ge=1, le=200)

    @field_validator("FALLBACK_ENCODING")
    @classmethod
    def validate_fallback_encoding(cls, value: str) -> str:
        try:
            codecs.lookup(value)
        except LookupError as e:
            raise ValueError(f"Unknown FALLBACK_ENCODING: {value}") from e
        return value

    @field_validator("EXPANSION_PROMPT_TEMPLATE")
    @classmethod
    def validate_expansion_prompt(cls, value: str) -> str:
        return _require_file("EXPANSION_PROMPT_TEMPLATE", value)

    @model_validator(mode="after")
    def validate_embedding_dimensions(self) -> Self:
        expected = _EMBEDDING_MODEL_DIMENSIONS.get(self.EMBEDDING_MODEL)
        if expected is not None and expected != self.EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"{self.EMBEDDING_MODEL} returns {expected} dimensions, but "
                f"EMBEDDING_DIMENSIONS is {self.EMBEDDING_DIMENSIONS}."
            )
        return self


class _WebSearchSettings(_BaseSettings):
    """
    Web search configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    BRAVE_API_KEY: SecretStr = Field(default=...)
    REQUEST_TIMEOUT_SECS: int = Field(
        default=10, ge=1, le=60, validation_alias="WEB_REQUEST_TIMEOUT_SECS"
    )
    # Brave returns at most 20 results per request
    MAX_SEARCH_RESULTS: int = Field(default=5, ge=1, le=20)
    MAX_WEB_RESULT_CHARS: int = Field(default=4000, ge=500, le=50000)
    USER_AGENT: str = Field(
        default="AskDocuMindBot/1.0 (+https://github.com/EmmanuelM-A/askdocumind)",
        min_length=10,
    )

    @field_validator("BRAVE_API_KEY")
    @classmethod
    def validate_brave_api_key(cls, value: SecretStr) -> SecretStr:
        return _require_secret("BRAVE_API_KEY", value)


class _LLMSettings(_BaseSettings):
    """
    Large Language Model (LLM) configuration settings for the AskDocuMind API application.
    """

    model_config = _DEFAULT_MODEL_CONFIG

    # Used by both the chat model and the embeddings
    OPENAI_API_KEY: SecretStr = Field(default=...)
    MODEL_NAME: str = Field(default="gpt-4o-mini", alias="LLM_MODEL_NAME")
    TEMPERATURE: float = Field(default=0.0, ge=0.0, le=2.0)
    REQUEST_TIMEOUT_SECS: int = Field(
        default=30, ge=1, le=300, alias="LLM_REQUEST_TIMEOUT_SECS"
    )
    MAX_RETRIES: int = Field(default=3, ge=0, le=10, alias="LLM_MAX_RETRIES")
    MAX_OUTPUT_TOKENS: int = Field(default=1024, ge=1, le=16000)

    # Answering
    ANSWER_PROMPT_TEMPLATE: str = Field(
        default=f"{_PROJECT_ROOT}/src/prompts/answer_prompt.yaml"
    )
    MAX_CONTEXT_CHARS: int = Field(default=40000, ge=1000, le=400000)

    @field_validator("OPENAI_API_KEY")
    @classmethod
    def validate_openai_api_key(cls, value: SecretStr) -> SecretStr:
        return _require_secret("OPENAI_API_KEY", value)

    @field_validator("ANSWER_PROMPT_TEMPLATE")
    @classmethod
    def validate_answer_prompt(cls, value: str) -> str:
        return _require_file("ANSWER_PROMPT_TEMPLATE", value)


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
    chat_session: _ChatSessionSettings = _ChatSessionSettings()
    uploads: _UploadSettings = _UploadSettings()
    rag: _RAGSettings = _RAGSettings()
    web: _WebSearchSettings = _WebSearchSettings()
    llm: _LLMSettings = _LLMSettings()

    @model_validator(mode="after")
    def validate_body_fits_file(self) -> Self:
        # Multipart adds boundaries and headers around the file, so the body
        # limit needs headroom above the file limit
        if self.server.MAX_REQUEST_BODY_SIZE_MB <= self.uploads.MAX_FILE_SIZE_MB:
            raise ValueError(
                "MAX_REQUEST_BODY_SIZE_MB must be greater than MAX_FILE_SIZE_MB."
            )
        return self


# Global settings instance
settings = _Settings()
