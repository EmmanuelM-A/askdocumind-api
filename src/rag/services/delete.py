"""
This module contains services related to the deletion of chunk embeddings.
"""

from uuid import UUID

from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.exceptions import forbidden_error, not_found_error
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.uploads.repository.document_repository import DocumentRepository


class DeleteChunkEmbeddingService:
    """
    Service responsible for deleting chunk embeddings from the database.
    """

    def __init__(
        self,
        chunk_embedding_repo: ChunkEmbeddingRepository,
        document_repository: DocumentRepository,
        chat_session_repository: ChatSessionRepository,
    ) -> None:
        self._chunk_embedding_repo = chunk_embedding_repo
        self._document_repository = document_repository
        self._chat_session_repository = chat_session_repository

    async def delete_by_document(self, chat_session_id: UUID, document_id: UUID) -> int:
        """
        Deletes all chunk embeddings that belong to a given document
        within a specific chat session.
        """
        document = await self._document_repository.get_by_id(document_id=document_id)

        if document is None:
            raise not_found_error(
                message="The specified file does not exist.",
                error_code="FILE_NOT_FOUND",
            )

        if document.chat_session_id != chat_session_id:
            raise forbidden_error(
                message="You do not have permission to delete chunk "
                "embeddings for this document.",
                error_code="OPERATION_FORBIDDEN",
            )

        return await self._chunk_embedding_repo.delete_by_document(
            document_id=document_id
        )

    async def delete_by_chat_session(self, chat_session_id: UUID) -> int:
        """
        Deletes all chunk embeddings that belong to a given chat session.
        """
        chat_session = await self._chat_session_repository.get_by_id(
            chat_session_id=chat_session_id
        )

        if chat_session is None:
            raise not_found_error(
                message="The specified chat session does not exist.",
                error_code="CHAT_SESSION_NOT_FOUND",
            )

        return await self._chunk_embedding_repo.delete_by_chat_session(
            chat_session_id=chat_session_id
        )
