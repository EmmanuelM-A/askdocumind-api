from enum import Enum


class ChatMessageRole(Enum):
    """Enum representing the role of a chat message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
