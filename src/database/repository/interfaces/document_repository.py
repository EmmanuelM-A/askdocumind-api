"""
Repository interface for document CRUD operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from src.database.models import Document
from src.config.constants import ProcessingStatus


class DocumentSearchCriteria(BaseModel):
    """Criteria for filtering documents in list/search operations."""

    id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    filename: Optional[str] = None
    vector_id: Optional[UUID] = None
    processing_status: Optional[ProcessingStatus] = None


class UpdatedDocumentData(BaseModel):
    """Schema for updating document fields."""

    filename: Optional[str] = None
    processing_status: Optional[ProcessingStatus] = None


class DocumentRepositoryInterface(ABC):
    """
    Abstract interface for document repository operations.

    Defines the contract for all document-related database operations.
    Concrete implementations must implement all abstract methods.
    """

    @abstractmethod
    async def create(self, data: Document) -> UUID:
        """
        Create and persist a new document entity.

        :param data: The Document entity to persist.
        :return: The UUID of the newly created document.
        :raises SQLAlchemyError: If database operation fails.
        :raises IntegrityError: If data integrity constraint is violated.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_by(
        self, criteria: Optional[DocumentSearchCriteria] = None
    ) -> List[Document]:
        """
        Retrieve documents matching the given criteria.

        Returns all documents if no criteria is provided.

        :param criteria: Optional search criteria to filter documents.
        :return: List of Document entities matching the criteria (empty list
            if none found).
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> Optional[Document]:
        """
        Retrieve a single document by its unique identifier.

        :param document_id: The UUID of the document to retrieve.
        :return: The Document entity if found, None otherwise.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_by_criteria(
        self, criteria: DocumentSearchCriteria
    ) -> Optional[Document]:
        """
        Retrieve a single document matching the given criteria.

        Returns the first match if multiple documents satisfy the criteria.

        :param criteria: The search criteria to filter by.
        :return: The first Document entity matching criteria, or None if not
            found.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, entity_id: UUID, new_entity_data: UpdatedDocumentData
    ) -> Optional[Document]:
        """
        Update an existing document with new data.

        :param entity_id: The UUID of the document to update.
        :param new_entity_data: The update payload containing new field values.
        :return: The updated Document entity if found, None otherwise.
        :raises SQLAlchemyError: If database operation fails.
        :raises IntegrityError: If data integrity constraint is violated.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, document_id: UUID) -> bool:
        """
        Delete a document by its unique identifier.

        :param document_id: The UUID of the document to delete.
        :return: True if document was deleted, False if not found.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if a document with the given UUID exists.

        :param entity_id: The UUID to check for existence.
        :return: True if document exists, False otherwise.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def count(self, filter_id: Optional[UUID] = None) -> int:
        """
        Count documents, optionally filtered by session ID.

        :param filter_id: Optional session UUID to filter by. If provided,
            counts only documents in that session.
        :return: The count of documents matching the filter.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    async def create_many(self, entities: List[Document]) -> List[UUID]:
        """
        Create and persist multiple document entities in a single transactional
        operation.

        All entities are persisted atomically: if any error occurs, the entire
        transaction is rolled back and no documents are created.

        :param entities: List of Document entities to persist.
        :return: List of UUIDs for the newly created documents.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    async def delete_many(self, document_ids: list[UUID]) -> int:
        """
        Delete multiple documents by their identifiers.

        :param document_ids: List of document UUIDs to delete.
        :return: The number of documents successfully deleted.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError

    async def bulk_update_processing_status(
        self, document_ids: List[UUID], status: ProcessingStatus
    ) -> int:
        """
        Update the processing status for multiple documents.

        :param document_ids: List of document UUIDs to update.
        :param status: The ProcessingStatus value to set for all documents.
        :return: The number of documents successfully updated.
        :raises SQLAlchemyError: If database operation fails.
        """
        raise NotImplementedError
