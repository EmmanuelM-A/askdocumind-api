"""
Storage factory for creating storage instances.

Centralizes storage creation logic and configuration.
"""

from typing import Type, TypeVar

from src.storage.storage_base import DatabaseStorageBase, FileStorageBase
from src.storage.postgresql_storage import PostgreSQLStorage
from src.storage.local_file_storage import LocalFileStorage
from src.config.configs import settings

T = TypeVar("T")


class StorageFactory:
    """
    Factory for creating storage instances.

    Usage:
        # Database storage
        from src.database.models import ChatSession
        session_storage = StorageFactory.get_database_storage(ChatSession)
        session_storage.create(session)

        # File storage
        file_storage = StorageFactory.get_file_storage()
        file_storage.upload(file_bytes, "sessions/123/doc.pdf")
    """

    @staticmethod
    def get_database_storage(model_class: Type[T]) -> DatabaseStorageBase[T]:
        """
        Get database storage instance for a model.

        Args:
            model_class: SQLAlchemy model class

        Returns:
            Database storage instance
        """
        # For now, always use PostgreSQL
        # Could be extended to support SQLite for testing
        return PostgreSQLStorage(model_class)

    @staticmethod
    def get_file_storage() -> FileStorageBase:
        """
        Get file storage instance based on environment.

        Returns:
            File storage instance (Local, S3, or MinIO)
        """
        # For now, use local file storage
        # In production, this would check settings and return S3/MinIO storage

        storage_type = getattr(settings.file, "STORAGE_TYPE", "local")

        if storage_type == "local":
            base_dir = getattr(settings.file, "STORAGE_BASE_DIR", "./data/storage")
            return LocalFileStorage(base_dir=base_dir)

        # Future implementations:
        # elif storage_type == 's3':
        #     return S3Storage(bucket=settings.file.S3_BUCKET)
        # elif storage_type == 'minio':
        #     return MinIOStorage(
        #         endpoint=settings.file.MINIO_ENDPOINT,
        #         bucket=settings.file.MINIO_BUCKET
        #     )

        raise ValueError(f"Unsupported storage type: {storage_type}")
