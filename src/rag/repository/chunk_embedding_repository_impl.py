from uuid import UUID

from fastapi_pagination import Page
from sqlalchemy import select, delete, Select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.utils import BaseRepository, Pagination
from src.exceptions import database_error
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.repository.chunk_embedding_repository import (
    ChunkEmbeddingRepository,
    CountByCriteria,
)


def _apply_criteria(statement: Select, criteria: CountByCriteria) -> Select:
    """Apply the given criteria to the SQLAlchemy statement."""

    if criteria.document_id is not None:
        statement = statement.where(ChunkEmbedding.document_id == criteria.document_id)

    if criteria.created_at is not None:
        statement = statement.where(ChunkEmbedding.created_at >= criteria.created_at)

    return statement


class ChunkEmbeddingRepositoryImpl(ChunkEmbeddingRepository, BaseRepository):
    """
    Concrete implementation of the ChunkEmbeddingRepository interface.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(self, data: ChunkEmbedding) -> ChunkEmbedding:
        try:
            self._session.add(data)
            await self._session.flush()
            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a new chunk embedding.",
                error_code="CHUNK_EMBEDDING_CREATION_ERROR",
                cause=e,
            ) from e

    async def list_by_chat_session(
        self, chat_session_id: UUID, paginate: Pagination
    ) -> Page[ChunkEmbedding]:
        statement = select(ChunkEmbedding).where(
            ChunkEmbedding.chat_session_id == chat_session_id
        )

        try:
            return await self._paginate(statement, paginate)
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chunk embeddings for "
                "the specified chat session.",
                error_code="CHUNK_EMBEDDING_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def get_by_id(self, chunk_id: UUID) -> ChunkEmbedding | None:
        statement = select(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id)
        try:
            result = await self._session.execute(statement)
            return result.scalar_one_or_none()
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving the chunk "
                "embedding by ID.",
                error_code="CHUNK_EMBEDDING_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def list_by_document(
        self, document_id: UUID, paginate: Pagination
    ) -> Page[ChunkEmbedding]:
        statement = select(ChunkEmbedding).where(
            ChunkEmbedding.document_id == document_id
        )

        try:
            return await self._paginate(statement, paginate)
        except Exception as e:
            raise database_error(
                message="An error occurred while listing chunk embeddings for "
                "the specified document.",
                error_code="CHUNK_EMBEDDING_RETRIEVAL_ERROR",
                cause=e,
            ) from e

    async def create_many(self, chunks: list[ChunkEmbedding]) -> int:
        try:
            self._session.add_all(chunks)
            await self._session.flush()
            return len(chunks)
        except Exception as e:
            raise database_error(
                message="An error occurred while creating multiple chunk embeddings.",
                error_code="CHUNK_EMBEDDING_CREATION_ERROR",
                cause=e,
            ) from e

    async def delete(self, chunk_id: UUID) -> None:
        statement = delete(ChunkEmbedding).where(ChunkEmbedding.id == chunk_id)
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting the chunk embedding.",
                error_code="CHUNK_EMBEDDING_DELETION_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message=f"No chunk embedding found with the provided ID.",
                error_code="CHUNK_EMBEDDING_NOT_FOUND",
            )

    async def delete_by_chat_session(self, chat_session_id: UUID) -> int:
        statement = delete(ChunkEmbedding).where(
            ChunkEmbedding.chat_session_id == chat_session_id
        )
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting chunk embeddings for "
                "the specified chat session.",
                error_code="CHUNK_EMBEDDING_DELETION_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message=f"No chunk embeddings found for the provided chat session ID.",
                error_code="CHUNK_EMBEDDING_NOT_FOUND",
            )

        return result.rowcount

    async def delete_by_document(self, document_id: UUID) -> int:
        statement = delete(ChunkEmbedding).where(
            ChunkEmbedding.document_id == document_id
        )
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting chunk embeddings for "
                "the specified document.",
                error_code="CHUNK_EMBEDDING_DELETION_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message=f"No chunk embeddings found for the provided document ID.",
                error_code="CHUNK_EMBEDDING_NOT_FOUND",
            )

        return result.rowcount

    async def get_candidate_chunk_embeddings(
        self, chat_session_id: UUID
    ) -> list[ChunkEmbedding]:
        """
        Retrieve candidate chunks for similarity search based on the chat session ID.
        """
        statement = select(ChunkEmbedding).where(
            ChunkEmbedding.chat_session_id == chat_session_id
        )

        try:
            result = await self._session.execute(statement)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while retrieving candidate chunks.",
                error_code="CANDIDATE_CHUNK_RETRIEVAL_ERROR",
            ) from e
