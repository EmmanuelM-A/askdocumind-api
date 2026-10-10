from uuid import UUID

from src.shared.utils import CamelCaseSerializer


class ViewableDocument(CamelCaseSerializer):
    """
    Represents a viewable document.
    """

    id: UUID
    chat_session_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    status: str
    error_message: str | None
    created_at: str
    updated_at: str
