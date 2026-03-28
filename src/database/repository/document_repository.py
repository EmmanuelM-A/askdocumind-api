"""
Repository module for document entities.
"""

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, update
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.models import Document
from src.database.repository.database_repository import DatabaseRepository
from src.config.constants import ProcessingStatus


class DocumentRepository(DatabaseRepository[Document]):
    """
    Repository specialization for document entities.
    """

    async def create(self, entity: Document) -> UUID:
        """
        Create a new document entry in the database.

        :param entity: Document entity to create.
        :return: The ID of the created document.

        :raises SQLAlchemyError: If a database error occurs during creation.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                session.add(entity)
                await session.flush()
                return entity.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def list_by(self, criteria: Optional[Document] = None) -> List[Document]:
        pass

    async def get_by_id(self, entity_id: UUID) -> Optional[Document]:
        """
        Retrieve a document by its ID or None if it does not exist.

        :param entity_id: The ID of the document to retrieve.
        :return: A document or None if it does not exist.

        :raises SQLAlchemyError: If a database error occurs during retrieval.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                if entity_id is None:
                    result = await session.execute(select(Document))
                    return result.scalars().all()

                # Use session.get for primary-key lookup (avoids SQL expression typing warnings)
                return await session.get(Document, entity_id)

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get_by_criteria(self, criteria: Document) -> Optional[Document]:
        pass

    async def update(
        self, entity_id: UUID, new_entity_data: Document
    ) -> Optional[Document]:
        """
        Update an existing document. Only writable fields are changed.

        :param entity_id: The ID of the document to update.
        :param new_entity_data: The new document data to apply.
        :return: The updated Document entity if successful, None if not found.

        :raises SQLAlchemyError: If a database error occurs during update.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                # Use session.get to fetch by primary key and avoid SQL expression typing issues
                existing = await session.get(Document, entity_id)

                if not existing:
                    return None

                # Update allowed fields for Document
                if (
                    hasattr(new_entity_data, "filename")
                    and new_entity_data.filename is not None
                ):
                    existing.filename = new_entity_data.filename
                if (
                    hasattr(new_entity_data, "file_size")
                    and new_entity_data.file_size is not None
                ):
                    existing.file_size = new_entity_data.file_size
                if (
                    hasattr(new_entity_data, "vector_id")
                    and new_entity_data.vector_id is not None
                ):
                    existing.vector_id = new_entity_data.vector_id
                if (
                    hasattr(new_entity_data, "processing_status")
                    and new_entity_data.processing_status is not None
                ):
                    existing.processing_status = new_entity_data.processing_status

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete a document by its ID.

        :param entity_id: The ID of the document to delete.
        :return: True if deleted, False if not found.

        :raises SQLAlchemyError: If a database error occurs during deletion.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                existing = await session.get(Document, entity_id)
                if not existing:
                    return False
                await session.delete(existing)
                await session.flush()
                return True

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if a document exists by its ID.

        :param entity_id: The ID of the document to check.
        :return: True if exists, False otherwise.

        :raises SQLAlchemyError: If a database error occurs during existence check.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                existing = await session.get(Document, entity_id)
                return existing is not None

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def count(self, filter_id: Optional[UUID] = None) -> int:
        """
        Count total documents, optionally filtered by owner ID or collection ID.

        :param filter_id: Optional filter ID (e.g., owner_id or collection_id).
        :return: Total count of documents.

        :raises SQLAlchemyError: If a database error occurs during counting.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                # Use func.count(Document.id) to avoid typing issues with func.count()
                # type: ignore[call-arg]
                stmt = select(func.count(Document.id)).select_from(Document)  # type: ignore
                if filter_id:
                    # Adjust based on your Document model's actual field
                    stmt = stmt.where(Document.owner_id == filter_id)  # type: ignore[arg-type]
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def bulk_update_processing_status(
        self, entity_ids: List[UUID], status: ProcessingStatus
    ) -> int:
        """
        Bulk update processing_status for multiple documents.

        :param entity_ids: List of document UUIDs to update.
        :param status: ProcessingStatus enum value to set.
        :return: Number of rows updated.
        """
        if not entity_ids:
            return 0

        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    update(Document)
                    .where(Document.id.in_(entity_ids))
                    .values(processing_status=status)
                )
                return result.rowcount

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
