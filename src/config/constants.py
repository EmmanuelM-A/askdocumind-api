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

