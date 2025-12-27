"""
Repository module for document entities.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.models import Document
from src.database.repository.database_repository import DatabaseRepository


class DocumentRepository(DatabaseRepository[Document]):
    """
    Repository specialization for document entities.
    """

    async def create(self, entity: Document) -> str:
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
                return str(entity.id)

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def get(self, entity_id: str) -> Optional[Document]:
        """
        Retrieve a document by its ID.

        :param entity_id: The ID of the document to retrieve.
        :return: The Document entity if found, None otherwise.

        :raises SQLAlchemyError: If a database error occurs during retrieval.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(Document).where(Document.id == UUID(entity_id))
                )
                return result.scalar_one_or_none()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def update(
        self, entity_id: str, new_entity_data: Document
    ) -> Optional[Document]:
        """
        Update an existing document.

        :param entity_id: The ID of the document to update.
        :param new_entity_data: The new document data to apply.
        :return: The updated Document entity if successful, None if not found.

        :raises SQLAlchemyError: If a database error occurs during update.
        :raises IntegrityError: If a data integrity violation occurs.
        :raises Exception: For any other exceptions that may arise.
        """
        try:
            async with self._db.get_session() as session:
                result = await session.execute(
                    select(Document).where(Document.id == UUID(entity_id))
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    return None

                # Update allowed fields
                if hasattr(new_entity_data, "title"):
                    existing.title = new_entity_data.title
                if hasattr(new_entity_data, "content"):
                    existing.content = new_entity_data.content
                if hasattr(new_entity_data, "metadata"):
                    existing.metadata = new_entity_data.metadata

                await session.flush()
                return existing

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def delete(self, entity_id: str) -> bool:
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
                result = await session.execute(
                    delete(Document).where(Document.id == UUID(entity_id))
                )
                return result.rowcount > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def exists(self, entity_id: str) -> bool:
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
                result = await session.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.id == UUID(entity_id))
                )
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e

    async def count(self, filter_id: Optional[str] = None) -> int:
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
                stmt = select(func.count()).select_from(Document)
                if filter_id:
                    # Adjust based on your Document model's actual field
                    stmt = stmt.where(Document.owner_id == UUID(filter_id))
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise e
