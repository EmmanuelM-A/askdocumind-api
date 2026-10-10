"""
Defines the interface for the chunk embedding repository, outlining the
operations that can be performed on chunk embeddings in the database.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from fastapi_pagination import Page
from pydantic import BaseModel

from src.database.utils import Pagination
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
    async def create(self, data: ChunkEmbedding) -> ChunkEmbedding:
        """
        Create a new Chunk Embedding for a resource.
        """
        raise NotImplementedError(
            "The method 'create' must be implemented by its subclass"
        )

    @abstractmethod
    async def list_by_chat_session(
        self, chat_session_id: UUID, paginate: Pagination
    ) -> Page[ChunkEmbedding]:
        """
        List all chunk embeddings to a specific chat session, with
        pagination support.
        """
        raise NotImplementedError(
            "The method 'list_by_chat_session' must be implemented by its subclass"
        )

    @abstractmethod
    async def get_by_id(self, chunk_id: UUID) -> ChunkEmbedding | None:
        """
        Retrieve a single chunk embedding by its id.
        """
        raise NotImplementedError(
            "The method 'get_by_id' must be implemented by its subclass"
        )

    @abstractmethod
    async def list_by_document(
        self, document_id: UUID, paginate: Pagination
    ) -> Page[ChunkEmbedding]:
        """
        List all chunk embeddings that belong to a document, with
        pagination support.
        """
        raise NotImplementedError(
            "The method 'list_by_document' must be implemented by its subclass"
        )

    @abstractmethod
    async def create_many(self, chunks: list[ChunkEmbedding]) -> int:
        """
        Create multiple chunk embeddings at once.
        """
        raise NotImplementedError(
            "The method 'create_many' must be implemented by its subclass"
        )

    @abstractmethod
    async def delete(self, chunk_id: UUID) -> None:
        """
        Delete a single chunk embedding by its id.
        """
        raise NotImplementedError(
            "The method 'delete' must be implemented by its subclass"
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
