"""
This module defines constants and enumerations used across the application.
"""

import enum


class ProcessingStatus(enum.Enum):
    """Enumeration for document processing statuses."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChatMessageRole(enum.Enum):
    """Enumeration for chat message roles."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class CacheNamespace(str, enum.Enum):
    """Enumeration for cache namespaces."""

    DEFAULT = "default"
    SESSIONS = "sessions"
    API_RESPONSES = "api_responses"
    EMBEDDINGS = "embeddings"
    QUERIES = "queries"
    DOCUMENTS = "documents"


class Source(str, enum.Enum):
    """Enumeration for document sources."""

    UPLOAD = "UPLOAD"
    WEB_SEARCH = "WEB_SEARCH"
    API = "API"
    OTHER = "OTHER"
