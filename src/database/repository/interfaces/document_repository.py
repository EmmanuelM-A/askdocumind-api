"""
Repository interface for document CRUD operations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.config.constants import DocumentSourceType, ProcessingStatus
from src.database.models import Document
from src.database.repository.interfaces.db_transaction import DBTransaction


class DocumentSearchCriteria(BaseModel):
    """Criteria for filtering documents in list/search operations."""

    id: UUID | None = None
    session_id: UUID | None = None
    source: str | None = None
    vector_id: UUID | None = None
    processing_status: ProcessingStatus | None = None
    source_type: DocumentSourceType | None = None


class UpdatedDocumentData(BaseModel):
    """Schema for updating document fields."""

    source: str | None = None
    processing_status: ProcessingStatus | None = None

class DocumentRepositoryInterface(ABC):
    """
    Abstract interface for document repository operations.

    Defines the contract for all document-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: Document, tx: DBTransaction | None = None) -> UUID:
        """
        Create and persist a new document entity.

        :param data: The Document entity to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The UUID of the newly created document.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by(
        self,
        criteria: DocumentSearchCriteria | None = None,
        tx: DBTransaction | None = None,
    ) -> list[Document]:
        """
        Retrieve documents matching the given criteria.

        Returns all documents if no criteria is provided.

        :param criteria: Optional search criteria to filter documents.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of Document entities matching the criteria (empty list
            if none found).
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(
        self, document_id: UUID, tx: DBTransaction | None = None
    ) -> Document | None:
        """
        Retrieve a single document by its unique identifier.

        :param document_id: The UUID of the document to retrieve.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The Document entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_criteria(
        self,
        criteria: DocumentSearchCriteria,
        tx: DBTransaction | None = None,
    ) -> Document | None:
        """
        Retrieve a single document matching the given criteria.

        Returns the first match if multiple documents satisfy the criteria.

        :param criteria: The search criteria to filter by.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The first Document entity matching criteria, or None if not
            found.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        entity_id: UUID,
        new_entity_data: UpdatedDocumentData,
        tx: DBTransaction | None = None,
    ) -> Document | None:
        """
        Update an existing document with new data.

        :param entity_id: The UUID of the document to update.
        :param new_entity_data: The update payload containing new field values.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The updated Document entity if found, None otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self, document_id: UUID, tx: DBTransaction | None = None
    ) -> bool:
        """
        Delete a document by its unique identifier.

        :param document_id: The UUID of the document to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if document was deleted, False if not found.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(
        self, entity_id: UUID, tx: DBTransaction | None = None
    ) -> bool:
        """
        Check if a document with the given UUID exists.

        :param entity_id: The UUID to check for existence.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: True if document exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(
        self,
        filter_id: UUID | None = None,
        tx: DBTransaction | None = None,
    ) -> int:
        """
        Count documents, optionally filtered by session ID.

        :param filter_id: Optional session UUID to filter by. If provided,
            counts only documents in that session.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The count of documents matching the filter.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_total_size_mb(
        self,
        chat_session_id: UUID,
        tx: DBTransaction | None = None,
    ) -> float:
        """
        Sum the stored document sizes and return the total in megabytes.

        :param chat_session_id: The UUID of the chat session to calculate total size for.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: Total document size in megabytes.
        """
        raise NotImplementedError

    async def create_many(
        self, entities: list[Document], tx: DBTransaction | None = None
    ) -> list[UUID]:
        """
        Create and persist multiple document entities in a single transactional
        operation.

        All entities are persisted atomically: if any error occurs, the entire
        transaction is rolled back and no documents are created.

        :param entities: List of Document entities to persist.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of UUIDs for the newly created documents.
        """
        raise NotImplementedError

    async def delete_many(
        self, document_ids: list[UUID], tx: DBTransaction | None = None
    ) -> int:
        """
        Delete multiple documents by their identifiers.

        :param document_ids: List of document UUIDs to delete.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The number of documents successfully deleted.
        """
        raise NotImplementedError

    async def bulk_update_processing_status(
        self,
        document_ids: list[UUID],
        status: ProcessingStatus,
        tx: DBTransaction | None = None,
    ) -> int:
        """
        Update the processing status for multiple documents.

        :param document_ids: List of document UUIDs to update.
        :param status: The ProcessingStatus value to set for all documents.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: The number of documents successfully updated.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_stuck_processing_ids(
        self, cutoff: datetime, tx: DBTransaction | None = None
    ) -> list[UUID]:
        """
        Return IDs of documents stuck in PROCESSING status since before the cutoff.

        :param cutoff: Datetime threshold; documents with updated_at <= cutoff are returned.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of document UUIDs in PROCESSING status older than the cutoff.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_all_failed_ids(
        self, cutoff: datetime, tx: DBTransaction | None = None
    ) -> list[UUID]:
        """
        Return IDs of FAILED documents whose updated_at is at or before the cutoff.

        :param cutoff: Datetime threshold; only FAILED docs updated before this are returned.
        :param tx: Optional db transaction to wrap a db operation in.
        :return: List of document UUIDs in FAILED status older than the cutoff.
        """
        raise NotImplementedError
