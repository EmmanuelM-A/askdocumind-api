from uuid import UUID

from src.shared.utils import CamelCaseSerializer


class ViewableChatSession(CamelCaseSerializer):
    """
    Represents a viewable chat session.
    """

    id: UUID
    title: str
    created_at: str


class ViewableChatMessage(CamelCaseSerializer):
    """
    Represents a viewable chat message.
    """

    id: UUID
    chat_session_id: UUID
    role: str
    content: str
    sources: list[str]
    created_at: str
