from uuid import UUID

from src.shared.utils import CamelCaseSerializer
from src.uploads.domain.document import ProcessingStatus


class ViewableDocument(CamelCaseSerializer):
    """
    Represents a viewable document.
    """

    id: UUID
    chat_session_id: UUID
    filename: str
    file_size: int
    processing_status: ProcessingStatus
    created_at: str
    updated_at: str
