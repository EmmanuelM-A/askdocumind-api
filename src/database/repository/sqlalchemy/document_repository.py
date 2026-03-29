"""
Concrete implementation of the document repository, providing methods for CRUD
operations and specific queries related to document entities.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.connection import DatabaseConnection
from src.database.models import Document
from src.config.constants import ProcessingStatus
from src.database.repository.interfaces.document_repository import (
    DocumentRepositoryInterface,
    DocumentSearchCriteria,
    UpdatedDocumentData,
)
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class DocumentRepository(DocumentRepositoryInterface):
    """
    Concrete implementation of the document repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    async def create(self, entity: Document) -> UUID:
        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()
                self._logger.debug(f"New document created: {entity.id}")
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new document.",
                error_code="DOCUMENT_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self, criteria: Optional[DocumentSearchCriteria] = None
    ) -> List[Document]:
        try:
            async with self._db.get_session() as session:
                stmt = select(Document)

                if criteria is None:
                    result = await session.execute(stmt)
                    self._logger.debug("No criteria provided, returning all documents")
                    return result.scalars().all()

                filters = []

                for field, value in criteria.model_dump(exclude_none=True).items():
                    filters.append(getattr(Document, field) == value)

                stmt = stmt.where(*filters)
                result = await session.execute(stmt)
                self._logger.debug("Found documents matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing documents by criteria.",
                error_code="DOCUMENT_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(self, entity_id: UUID) -> Optional[Document]:
        try:
            async with self._db.get_session() as session:
                result = await session.get(Document, entity_id)
                if result:
                    self._logger.debug(f"Found document: {entity_id}")
                return result

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document by id.",
                error_code="DOCUMENT_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self, criteria: DocumentSearchCriteria
    ) -> Optional[Document]:
        try:
            filters = []

            for field, value in criteria.model_dump(exclude_none=True).items():
                filters.append(getattr(Document, field) == value)

            if not filters:
                self._logger.debug("No criteria provided for get_by_criteria")
                return None

            async with self._db.get_session() as session:
                result = await session.execute(select(Document).where(*filters))
                self._logger.debug("Found document matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document by criteria.",
                error_code="DOCUMENT_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self, document_id: UUID, updated_data: UpdatedDocumentData
    ) -> Optional[Document]:
        try:
            async with self._db.get_session() as session:
                existing = await session.get(Document, document_id)

                if not existing:
                    return None

                if (
                    hasattr(updated_data, "filename")
                    and updated_data.filename is not None
                ):
                    existing.filename = updated_data.filename
                if (
                    hasattr(updated_data, "processing_status")
                    and updated_data.processing_status is not None
                ):
                    existing.processing_status = updated_data.processing_status

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating document.",
                error_code="DOCUMENT_UPDATE_ERROR",
                stack_trace=str(e),
            )

    async def delete(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                existing = await session.get(Document, entity_id)
                if not existing:
                    return False
                await session.delete(existing)
                await session.flush()
                return True

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting document.",
                error_code="DOCUMENT_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, entity_id: UUID) -> bool:
        try:
            async with self._db.get_session() as session:
                existing = await session.get(Document, entity_id)
                return existing is not None

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if document exists.",
                error_code="DOCUMENT_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(self, filter_id: Optional[UUID] = None) -> int:
        try:
            async with self._db.get_session() as session:
                stmt = select(func.count(Document.id)).select_from(Document)  # type: ignore
                if filter_id:
                    stmt = stmt.where(Document.session_id == filter_id)  # type: ignore[arg-type]
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting documents.",
                error_code="DOCUMENT_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(self, entities: List[Document]) -> List[UUID]:
        if not entities:
            return []

        try:
            async with self._db.get_session() as session:
                session.add_all(entities)
                await session.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} document entries")
                return created_ids

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating multiple documents.",
                error_code="DOCUMENT_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def delete_many(self, document_ids: list[UUID]) -> int:
        if not document_ids:
            return 0

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    delete(Document).where(Document.id.in_(document_ids))
                )
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} document entries")
                return deleted_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting multiple documents.",
                error_code="DOCUMENT_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def bulk_update_processing_status(
        self, document_ids: List[UUID], status: ProcessingStatus
    ) -> int:
        if not document_ids:
            return 0

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    update(Document)
                    .where(Document.id.in_(document_ids))
                    .values(processing_status=status)
                )
                updated_count = result.rowcount or 0
                self._logger.debug(
                    f"Updated processing status for {updated_count} documents"
                )
                return updated_count

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating processing statuses.",
                error_code="DOCUMENT_UPDATE_ERROR",
                stack_trace=str(e),
            )
