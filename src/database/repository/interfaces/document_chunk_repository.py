"""
Repository interface for document chunk (embedding) CRUD operations.

This interface defines operations that will be useful both for the current
FAISS-based retrieval and the planned pgvector-backed implementation. Keep
the surface area minimal but practical for chunk creation, lookup, bulk
operations and similarity search hooks.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from src.database.models import DocumentChunk
from src.database.repository.interfaces.db_transaction import DBTransaction


class DocumentChunkSearchCriteria(BaseModel):
    """Criteria for filtering document chunks in list/search operations."""

    id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    chunk_index: Optional[int] = None


class UpdatedDocumentChunkData(BaseModel):
    """Schema for updating document chunk fields."""

    chunk_text: Optional[str] = None
    # Embedding updates may be supported by some implementations; keep it
    # generic (implementation may accept list[float] if applicable).
    embedding: Optional[object] = None


class DocumentChunkRepositoryInterface(ABC):
    """
    Abstract interface for document chunk repository operations.

    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(
        self, data: DocumentChunk, tx: Optional[DBTransaction] = None
    ) -> UUID:
        """
        Persist a new document chunk (embedding) record.

        :param data: The DocumentChunk entity to persist.
        :param tx: Optional DBTransaction to run the operation under.
        :return: UUID of the newly created chunk.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by(
        self,
        criteria: Optional[DocumentChunkSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[DocumentChunk]:
        """
        Retrieve document chunks matching the provided criteria. If no
        criteria is provided, return all chunks (use with care).

        :param criteria: Optional search criteria.
        :param tx: Optional DBTransaction to run the operation under.
        :return: List of matching DocumentChunk entities.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self, chunk_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[DocumentChunk]:
        """
        Retrieve a single chunk by its UUID.

        :param chunk_id: UUID of the chunk.
        :param tx: Optional DBTransaction.
        :return: DocumentChunk or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_criteria(
        self, criteria: DocumentChunkSearchCriteria, tx: Optional[DBTransaction] = None
    ) -> Optional[DocumentChunk]:
        """
        Retrieve the first chunk matching the given criteria.

        :param criteria: Search criteria.
        :param tx: Optional DBTransaction.
        :return: The first matching DocumentChunk or None.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by_document_id(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> List[DocumentChunk]:
        """
        Convenience method to fetch all chunks for a document.

        :param document_id: UUID of the Document entity.
        :param tx: Optional DBTransaction.
        :return: List of DocumentChunk entities for the document.
        """
        raise NotImplementedError

    @abstractmethod
    async def upsert_many(
        self, chunks: List[DocumentChunk], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        """
        Insert or update multiple chunks in a single operation.

        Implementations may choose the most efficient bulk mechanism for the
        backend (batch insert, COPY, upsert, etc.).

        :param chunks: List of DocumentChunk entities to persist.
        :param tx: Optional DBTransaction.
        :return: List of UUIDs for persisted chunks.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, chunk_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        """
        Delete a single chunk by its UUID.

        :param chunk_id: UUID of the chunk to delete.
        :param tx: Optional DBTransaction.
        :return: True if deleted, False if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_document_id(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> int:
        """
        Delete all chunks associated with a document.

        :param document_id: UUID of the document whose chunks should be removed.
        :param tx: Optional DBTransaction.
        :return: Number of chunks deleted.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, chunk_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        """
        Check whether a chunk exists by UUID.

        :param chunk_id: UUID to check.
        :param tx: Optional DBTransaction.
        :return: True if exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(
        self, document_id: Optional[UUID] = None, tx: Optional[DBTransaction] = None
    ) -> int:
        """
        Count chunks, optionally filtered by document.

        :param document_id: Optional document UUID to filter by.
        :param tx: Optional DBTransaction.
        :return: Number of chunks matching the filter.
        """
        raise NotImplementedError

    @abstractmethod
    async def search_similar(
        self,
        chat_session_id: UUID,
        vector: List[float],
        top_k: int = 10,
        threshold: Optional[float] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[DocumentChunk]:
        """
        Search for chunks similar to the provided embedding vector.

        Concrete backends may return scored results; the interface keeps the
        return type simple (list of DocumentChunk). Implementations that
        provide scores can attach them to the returned entities or expose a
        different API.

        :param chat_session_id: The chat session ID.
        :param vector: Query embedding vector.
        :param top_k: Maximum number of results to return.
        :param threshold: Optional similarity/distance threshold to filter results.
        :param tx: Optional DBTransaction.
        :return: List of matching DocumentChunk entities.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_filenames_for_chunks(
        self,
        chunks: List[DocumentChunk],
        chat_session_id: UUID,
        tx: Optional[DBTransaction] = None,
    ) -> List[str]:
        """
        Retrieves unique filenames for all documents associated with the given chunks.
        Results are filtered to only include documents from the specified chat_session_id.

        :param chunks: List of DocumentChunk objects to extract document_ids from.
        :param chat_session_id: The chat session ID to filter documents by.
        :param tx: Optional database transaction.
        :return: List of unique filenames (no duplicates) from the specified chat session.
        """
        raise NotImplementedError

