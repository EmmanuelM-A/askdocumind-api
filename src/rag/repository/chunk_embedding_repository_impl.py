from uuid import UUID

from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from src.database.utils import BaseRepository
from src.exceptions.decorators import (
    handle_database_unavailable_exceptions,
    handle_sqlalchemy_exceptions,
    handle_database_integrity_exceptions,
)
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document


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

    @handle_sqlalchemy_exceptions(
        message="An error occurred while searching for similar chunk embeddings.",
        error_code="CHUNK_EMBEDDING_SEARCH_ERROR",
    )
    @handle_database_unavailable_exceptions()
    async def search_by_similarity(
        self,
        chat_session_id: UUID,
        vector: list[float],
        min_similarity: float,
        limit: int,
    ) -> list[ChunkEmbedding]:
        # The HNSW index is searched before the chat session filter is
        # applied, so without an iterative scan a busy table can return fewer
        # rows than the limit, or none at all.
        await self._session.execute(
            text("SET LOCAL hnsw.iterative_scan = strict_order")
        )

        distance = ChunkEmbedding.embedding.cosine_distance(vector)

        result = await self._session.execute(
            select(ChunkEmbedding)
            .join(Document, Document.id == ChunkEmbedding.document_id)
            # Fill chunk.document from the join so its filename can be read
            # without a lazy load, which async sessions do not allow.
            .options(contains_eager(ChunkEmbedding.document))
            .where(
                ChunkEmbedding.chat_session_id == chat_session_id,
                Document.status == DocumentStatus.COMPLETED,
                # Cosine distance is 1 - cosine similarity.
                distance <= 1 - min_similarity,
            )
            .order_by(distance)
            .limit(limit)
        )
        return list(result.scalars().all())
