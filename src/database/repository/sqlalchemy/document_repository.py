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
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.errors.custom_exceptions import conflict_error, database_error
from src.logger.base_logger import BaseLogger


class DocumentRepository(DocumentRepositoryInterface):
    """
    Concrete implementation of the document repository interface.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    @staticmethod
    def _build_filters(criteria: DocumentSearchCriteria) -> list:
        filters = []
        for field, value in criteria.model_dump(exclude_none=True).items():
            filters.append(getattr(Document, field) == value)
        return filters

    @staticmethod
    def _is_duplicate_filename_error(error: IntegrityError) -> bool:
        message = str(error).lower()
        return (
            "uq_document_session_filename" in message
            or "unique constraint" in message and "document" in message
        )

    async def create(self, data: Document, tx: Optional[DBTransaction] = None) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New document created: {data.id}")
                return data.id

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New document created: {data.id}")
                return data.id

        except IntegrityError as e:
            if self._is_duplicate_filename_error(e):
                raise conflict_error(
                    message="A document with the same filename already exists for this chat.",
                    error_code="DOCUMENT_ALREADY_EXISTS",
                    error_details=str(e.orig) if getattr(e, "orig", None) else None,
                )
            raise database_error(
                message="An error occurred while creating a new document.",
                error_code="DOCUMENT_CREATION_ERROR",
                stack_trace=str(e),
            )
        except (SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a new document.",
                error_code="DOCUMENT_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self,
        criteria: Optional[DocumentSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[Document]:
        try:
            stmt = select(Document)

            if criteria is not None:
                stmt = stmt.where(*self._build_filters(criteria))

            if tx is not None:
                result = await tx.execute(stmt)
                if criteria is None:
                    self._logger.debug("No criteria provided, returning all documents")
                else:
                    self._logger.debug("Found documents matching criteria")
                return result.scalars().all()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                if criteria is None:
                    self._logger.debug("No criteria provided, returning all documents")
                    return result.scalars().all()
                self._logger.debug("Found documents matching criteria")
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing documents by criteria.",
                error_code="DOCUMENT_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[Document]:
        try:
            stmt = select(Document).where(Document.id == document_id)

            if tx is not None:
                result = await tx.execute(stmt)
                document = result.scalar_one_or_none()
                if document:
                    self._logger.debug(f"Found document: {document_id}")
                return document

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()
                if document:
                    self._logger.debug(f"Found document: {document_id}")
                return document

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document by id.",
                error_code="DOCUMENT_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self,
        criteria: DocumentSearchCriteria,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[Document]:
        try:
            filters = self._build_filters(criteria)

            if not filters:
                self._logger.debug("No criteria provided for get_by_criteria")
                return None

            stmt = select(Document).where(*filters)

            if tx is not None:
                result = await tx.execute(stmt)
                self._logger.debug("Found document matching criteria")
                return result.scalars().first()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                self._logger.debug("Found document matching criteria")
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document by criteria.",
                error_code="DOCUMENT_GET_ERROR",
                stack_trace=str(e),
            )

    async def update(
        self,
        entity_id: UUID,
        new_entity_data: UpdatedDocumentData,
        tx: Optional[DBTransaction] = None,
    ) -> Optional[Document]:
        try:
            stmt = select(Document).where(Document.id == entity_id)

            if tx is not None:
                result = await tx.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_entity_data, "filename")
                    and new_entity_data.filename is not None
                ):
                    existing.filename = new_entity_data.filename
                if (
                    hasattr(new_entity_data, "processing_status")
                    and new_entity_data.processing_status is not None
                ):
                    existing.processing_status = new_entity_data.processing_status

                await tx.flush()
                return existing

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                if (
                    hasattr(new_entity_data, "filename")
                    and new_entity_data.filename is not None
                ):
                    existing.filename = new_entity_data.filename
                if (
                    hasattr(new_entity_data, "processing_status")
                    and new_entity_data.processing_status is not None
                ):
                    existing.processing_status = new_entity_data.processing_status

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while updating document.",
                error_code="DOCUMENT_UPDATE_ERROR",
                stack_trace=str(e),
            )

    async def delete(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> bool:
        try:
            stmt = delete(Document).where(Document.id == document_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return (result.rowcount or 0) > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return (result.rowcount or 0) > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting document.",
                error_code="DOCUMENT_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, entity_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        try:
            stmt = (
                select(func.count())
                .select_from(Document)
                .where(Document.id == entity_id)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one() > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while determining if document exists.",
                error_code="DOCUMENT_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(
        self,
        filter_id: Optional[UUID] = None,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        try:
            stmt = select(func.count(Document.id)).select_from(Document)
            if filter_id:
                stmt = stmt.where(Document.session_id == filter_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting documents.",
                error_code="DOCUMENT_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def create_many(
        self, entities: List[Document], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        if not entities:
            return []

        try:
            if tx is not None:
                await tx.add_all(entities)
                await tx.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} document entries")
                return created_ids

            async with self._db.get_session() as session:
                session.add_all(entities)
                await session.flush()
                created_ids = [entity.id for entity in entities]
                self._logger.debug(f"Created {len(created_ids)} document entries")
                return created_ids

        except IntegrityError as e:
            if self._is_duplicate_filename_error(e):
                raise conflict_error(
                    message="A document with the same filename already exists for this chat.",
                    error_code="DOCUMENT_ALREADY_EXISTS",
                    error_details=str(e.orig) if getattr(e, "orig", None) else None,
                )
            raise database_error(
                message="An error occurred while creating multiple documents.",
                error_code="DOCUMENT_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )
        except (SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating multiple documents.",
                error_code="DOCUMENT_BULK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def delete_many(
        self, document_ids: list[UUID], tx: Optional[DBTransaction] = None
    ) -> int:
        if not document_ids:
            return 0

        try:
            stmt = delete(Document).where(Document.id.in_(document_ids))

            if tx is not None:
                result = await tx.execute(stmt)
                deleted_count = result.rowcount or 0
                self._logger.debug(f"Deleted {deleted_count} document entries")
                return deleted_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
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
        self,
        document_ids: List[UUID],
        status: ProcessingStatus,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        if not document_ids:
            return 0

        try:
            stmt = (
                update(Document)
                .where(Document.id.in_(document_ids))
                .values(processing_status=status)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                updated_count = result.rowcount or 0
                self._logger.debug(
                    f"Updated processing status for {updated_count} documents"
                )
                return updated_count

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
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
