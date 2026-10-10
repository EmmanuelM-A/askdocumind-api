"""
This module contains data models and mappers for embeddings used in the
application.
"""

from uuid import UUID

from src.shared.utils import CamelCaseSerializer


class ViewableChunkEmbedding(CamelCaseSerializer):
    """
    Represents a viewable chunk embedding with its associated metadata.
    """

    id: UUID
    document_id: UUID
    chat_session_id: UUID
    chunk_text: str
    created_at: str
    updated_at: str | None
