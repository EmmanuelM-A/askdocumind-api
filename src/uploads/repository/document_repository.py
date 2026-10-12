"""
Repository interface for document CRUD operations.
"""

from abc import ABC, abstractmethod
from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from fastapi_pagination import Page
from pydantic import BaseModel

from src.database.utils import Pagination
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document


class DocumentSearchFilter(BaseModel):
    """Represents the search criteria for filtering documents."""

    filename: str | None = None
    status: DocumentStatus | None = None


class DocumentRepository(ABC):
    """
    Abstract interface for document repository operations.

    Defines the contract for all document-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: Document) -> Document:
        """
        Create and persist a new document entity.
        """
        raise NotImplementedError(
            "The 'create' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def list_by_criteria(
        self,
        chat_session_id: UUID,
        criteria: DocumentSearchFilter | None = None,
    ) -> list[Document]:
        """
        Retrieve documents matching the given criteria, sorted by creation
        date and ID in descending order (most recent first).
        """
        raise NotImplementedError(
            "The 'list_by_criteria' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def list_by_criteria_paginated(
        self,
        chat_session_id: UUID,
        paginate: Pagination,
        criteria: DocumentSearchFilter | None = None,
    ) -> Page[Document]:
        """
        Retrieve documents matching the given criteria, with pagination,
        sorted by creation date and ID in descending order (most recent first).
        """
        raise NotImplementedError(
            "The 'list_by_criteria_paginated' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> Document | None:
        """
        Retrieve a single document by its unique identifier.
        """
        raise NotImplementedError(
            "The 'get_by_id' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def delete(self, document_id: UUID) -> None:
        """
        Delete a document by its unique identifier.
        """
        raise NotImplementedError(
            "The 'delete' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def count(self, chat_session_id: UUID) -> int:
        """
        Count documents belonging to a specific chat session.
        """
        raise NotImplementedError(
            "The 'count' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def create_many(self, entities: list[Document]) -> list[UUID]:
        """
        Create and persist multiple document entities in a single operation.
        """
        raise NotImplementedError(
            "The 'create_many' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def delete_many(self, document_ids: list[UUID]) -> int:
        """
        Delete multiple documents by their identifiers.
        """
        raise NotImplementedError(
            "The 'delete_many' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def update_document_status(
        self,
        document_id: UUID,
        new_status: DocumentStatus,
        error_message: str | None = None,
    ) -> None:
        """
        Update the status of a document.
        """
        raise NotImplementedError(
            "The 'update_document_status' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def transition_document_status(
        self,
        document_id: UUID,
        from_statuses: Collection[DocumentStatus],
        to_status: DocumentStatus,
        error_message: str | None = None,
    ) -> bool:
        """
        Move a document to to_status only when its current status is in
        from_statuses. Return True when the row changed, False otherwise.
        """
        raise NotImplementedError(
            "The 'transition_document_status' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def list_stale_documents(
        self,
        status: DocumentStatus,
        older_than: datetime,
        limit: int = 100,
    ) -> list[Document]:
        """
        Return up to limit documents in the given status whose updated_at is
        before older_than, oldest first. Rows are locked with SKIP LOCKED until
        the transaction ends.
        """
        raise NotImplementedError(
            "The 'list_stale_documents' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def mark_uploaded(
        self, document_id: UUID, size_bytes: int, checksum: str
    ) -> bool:
        """
        Mark a document as uploaded, setting its size and checksum.
        Returns True if the document was updated, False otherwise.
        """
        raise NotImplementedError(
            "The 'mark_uploaded' method must be implemented by its subclasses."
        )

    @abstractmethod
    async def count(self, chat_session_id: UUID) -> int:
        """
        Count documents belonging to a specific chat session.
        """
        raise NotImplementedError(
            "The 'count' method must be implemented by its subclasses."
        )
