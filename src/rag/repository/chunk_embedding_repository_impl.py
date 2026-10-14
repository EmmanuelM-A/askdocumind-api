from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.utils import BaseRepository
from src.exceptions.decorators import (
    handle_database_unavailable_exceptions,
    handle_sqlalchemy_exceptions,
    handle_database_integrity_exceptions,
)
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository


class ChunkEmbeddingRepositoryImpl(ChunkEmbeddingRepository, BaseRepository):
    """
    Concrete implementation of the ChunkEmbeddingRepository interface.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @handle_sqlalchemy_exceptions(
        message="An error occurred while creating multiple chunk embeddings.",
        error_code="CHUNK_EMBEDDING_CREATION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    @handle_database_integrity_exceptions(
        message="One or more chunk embeddings already exist for the given "
        "document and chunk index.",
        error_code="CHUNK_EMBEDDING_INTEGRITY_ERROR",
    )
    async def create_many(self, chunks: list[ChunkEmbedding]) -> int:
        self._session.add_all(chunks)
        await self._session.flush()
        return len(chunks)

    @handle_sqlalchemy_exceptions(
        message="An error occurred while deleting chunk embeddings for "
        "the specified chat session.",
        error_code="CHUNK_EMBEDDING_DELETION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def delete_by_chat_session(self, chat_session_id: UUID) -> int:
        result = await self._session.execute(
            delete(ChunkEmbedding).where(
                ChunkEmbedding.chat_session_id == chat_session_id
            )
        )
        return result.rowcount

    @handle_sqlalchemy_exceptions(
        message="An error occurred while deleting chunk embeddings for "
        "the specified document.",
        error_code="CHUNK_EMBEDDING_DELETION_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def delete_by_document(self, document_id: UUID) -> int:
        result = await self._session.execute(
            delete(ChunkEmbedding).where(ChunkEmbedding.document_id == document_id)
        )
        return result.rowcount

    @handle_sqlalchemy_exceptions(
        message="An error occurred while retrieving candidate chunk embeddings.",
        error_code="CHUNK_EMBEDDING_RETRIEVAL_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def get_candidate_chunk_embeddings(
        self, chat_session_id: UUID
    ) -> list[ChunkEmbedding]:
        result = await self._session.execute(
            select(ChunkEmbedding).where(
                ChunkEmbedding.chat_session_id == chat_session_id
            )
        )
        return list(result.scalars().all())
