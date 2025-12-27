"""
PostgreSQL database storage implementation.

Used for storing structured metadata (users, sessions, documents).
"""

from typing import Optional, List, Any, Type, TypeVar
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.storage.storage_base import DatabaseStorageBase
from src.database.connection import get_db
from src.logger.base_logger import BaseLogger
from src.errors.custom_exceptions import throw_server_error

T = TypeVar("T")


class PostgreSQLStorage(DatabaseStorageBase[T]):
    """
    PostgreSQL storage implementation using SQLAlchemy.

    Generic storage for any SQLAlchemy model.
    """

    def __init__(self, model_class: Type[T]):
        """
        Initialize PostgreSQL storage.

        Args:
            model_class: SQLAlchemy model class to store
        """
        self.model_class = model_class
        self._logger = BaseLogger(__name__)

    def create(self, entity: T, entity_id: Optional[str] = None) -> str:
        """Create entity in database."""
        db: Session = next(get_db())

        try:
            # Set ID if provided
            if entity_id:
                entity.id = entity_id
            elif not hasattr(entity, "id") or not entity.id:
                entity.id = str(uuid4())

            db.add(entity)
            db.commit()
            db.refresh(entity)

            self._logger.info(
                f"Created {self.model_class.__name__} with ID: {entity.id}"
            )
            return entity.id

        except IntegrityError as e:
            db.rollback()
            throw_server_error(
                message=f"Failed to create {self.model_class.__name__}",
                error_code="DB_INTEGRITY_ERROR",
                stack_trace=str(e),
            )
        finally:
            db.close()

    def get(self, entity_id: str) -> Optional[T]:
        """Get entity by ID."""
        db: Session = next(get_db())

        try:
            entity = (
                db.query(self.model_class)
                .filter(self.model_class.id == entity_id)
                .first()
            )
            return entity
        finally:
            db.close()

    def update(self, entity_id: str, entity: T) -> Optional[T]:
        """Update entity."""
        db: Session = next(get_db())

        try:
            existing = (
                db.query(self.model_class)
                .filter(self.model_class.id == entity_id)
                .first()
            )

            if not existing:
                return None

            # Update fields
            for key, value in entity.__dict__.items():
                if not key.startswith("_"):
                    setattr(existing, key, value)

            db.commit()
            db.refresh(existing)

            self._logger.info(f"Updated {self.model_class.__name__} ID: {entity_id}")
            return existing

        except Exception as e:
            db.rollback()
            throw_server_error(
                message=f"Failed to update {self.model_class.__name__}",
                error_code="DB_UPDATE_ERROR",
                stack_trace=str(e),
            )
        finally:
            db.close()

    def delete(self, entity_id: str) -> bool:
        """Delete entity."""
        db: Session = next(get_db())

        try:
            entity = (
                db.query(self.model_class)
                .filter(self.model_class.id == entity_id)
                .first()
            )

            if not entity:
                return False

            db.delete(entity)
            db.commit()

            self._logger.info(f"Deleted {self.model_class.__name__} ID: {entity_id}")
            return True

        except Exception as e:
            db.rollback()
            throw_server_error(
                message=f"Failed to delete {self.model_class.__name__}",
                error_code="DB_DELETE_ERROR",
                stack_trace=str(e),
            )
        finally:
            db.close()

    def exists(self, entity_id: str) -> bool:
        """Check if entity exists."""
        db: Session = next(get_db())

        try:
            count = (
                db.query(self.model_class)
                .filter(self.model_class.id == entity_id)
                .count()
            )
            return count > 0
        finally:
            db.close()

    def list(self, entity_ids: Optional[List[str]] = None) -> List[T]:
        """List entities."""
        db: Session = next(get_db())

        try:
            query = db.query(self.model_class)

            if entity_ids:
                query = query.filter(self.model_class.id.in_(entity_ids))

            return query.all()
        finally:
            db.close()

    def query(self, filters: dict[str, Any]) -> List[T]:
        """Query with filters."""
        db: Session = next(get_db())

        try:
            query = db.query(self.model_class)

            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)

            return query.all()
        finally:
            db.close()

    def bulk_create(self, entities: List[T]) -> List[str]:
        """Bulk create entities."""
        db: Session = next(get_db())

        try:
            entity_ids = []

            for entity in entities:
                if not hasattr(entity, "id") or not entity.id:
                    entity.id = str(uuid4())
                entity_ids.append(entity.id)

            db.bulk_save_objects(entities)
            db.commit()

            self._logger.info(
                f"Bulk created {len(entities)} {self.model_class.__name__} records"
            )
            return entity_ids

        except Exception as e:
            db.rollback()
            throw_server_error(
                message=f"Failed to bulk create {self.model_class.__name__}",
                error_code="DB_BULK_CREATE_ERROR",
                stack_trace=str(e),
            )
        finally:
            db.close()
