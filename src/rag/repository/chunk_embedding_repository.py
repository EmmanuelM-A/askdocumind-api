"""
Defines the interface for the chunk embedding repository, outlining the
operations that can be performed on chunk embeddings in the database.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.rag.models.chunk_embedding import ChunkEmbedding


class CountByCriteria(BaseModel):
    """
    Represents the optional criteria for counting chunk embeddings.
    """

    document_id: UUID | None = None
    created_at: datetime | None = None


class ChunkEmbeddingRepository(ABC):
    """
    Interface defining all the chunk embedding operations
    """

    @abstractmethod
    async def create_many(self, chunks: list[ChunkEmbedding]) -> int:
        """
        Create multiple chunk embeddings at once.
        """
        raise NotImplementedError(
            "The method 'create_many' must be implemented by its subclass"
        )

    @abstractmethod
    async def delete_by_chat_session(self, chat_session_id: UUID) -> int:
        """
        Delete all chunk embeddings associated with a chat session.
        """
        raise NotImplementedError(
            "The method 'delete_by_chat_session' must be implemented by its subclass"
        )

    @abstractmethod
    async def delete_by_document(self, document_id: UUID) -> int:
        """
        Delete all chunk embeddings associated with a document.
        """
        raise NotImplementedError(
            "The method 'delete_by_document' must be implemented by its subclass"
        )

    @abstractmethod
    async def get_candidate_chunk_embeddings(
        self, chat_session_id: UUID
    ) -> list[ChunkEmbedding]:
        """
        Retrieves a list of candidate chunk embeddings for a given chat
        session.
        """
        raise NotImplementedError(
            "The method 'get_candidate_chunk_embeddings' must be implemented "
            "by its subclass"
        )

    @abstractmethod
    async def search_by_similarity(
        self,
        chat_session_id: UUID,
        vector: list[float],
        min_similarity: float,
        limit: int,
    ) -> list[ChunkEmbedding]:
        """
        Returns up to `limit` chunks from the completed documents of a chat
        session whose cosine similarity to the vector is at least
        `min_similarity`, most similar first.
        """
        raise NotImplementedError(
            "The method 'search_by_similarity' must be implemented by its subclass"
        )
