"""
Storage abstraction layer for DocuChat application.

Provides base interfaces for different storage backends:
- DatabaseStorageBase: For structured data (PostgresSQL)
- FileStorageBase: For unstructured data (File System, S3, MinIO)
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, Generic, TypeVar, List

# Generic type for entities stored
T = TypeVar("T")


class StorageBase(ABC, Generic[T]):
    """
    Abstract base class for all storage implementations.

    Defines the contract that all storage backends must implement.
    Supports CRUD operations and bulk queries.
    """

    @abstractmethod
    def create(self, entity: T) -> str:
        """
        Create a new entity in storage.

        Args:
            entity: The entity to store

        Returns:
            The ID of the created entity

        Raises:
            StorageException: If creation fails
        """
        raise NotImplementedError("Subclasses must implement create()")

    @abstractmethod
    def get(self, entity_id: str) -> Optional[T]:
        """
        Retrieve an entity by ID.

        Args:
            entity_id: The unique identifier

        Returns:
            The entity if found, None otherwise
        """
        raise NotImplementedError("Subclasses must implement get()")

    @abstractmethod
    def update(self, entity_id: str, entity: T) -> Optional[T]:
        """
        Update an existing entity.

        Args:
            entity_id: The unique identifier
            entity: The updated entity data

        Returns:
            The updated entity if successful, None if not found

        Raises:
            StorageException: If update fails
        """
        raise NotImplementedError("Subclasses must implement update()")

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """
        Delete an entity by ID.

        Args:
            entity_id: The unique identifier

        Returns:
            True if deleted, False if not found

        Raises:
            StorageException: If deletion fails
        """
        raise NotImplementedError("Subclasses must implement delete()")

    @abstractmethod
    def exists(self, entity_id: str) -> bool:
        """
        Check if an entity exists.

        Args:
            entity_id: The unique identifier

        Returns:
            True if exists, False otherwise
        """
        raise NotImplementedError("Subclasses must implement exists()")

    @abstractmethod
    def list(self, entity_ids: Optional[List[str]] = None) -> List[T]:
        """
        List multiple entities.

        Args:
            entity_ids: Optional list of IDs to retrieve.
                       If None, returns all entities (use with caution!)

        Returns:
            List of entities
        """
        raise NotImplementedError("Subclasses must implement list()")

    def count(self) -> int:
        """
        Count total entities in storage.

        Returns:
            Total count of entities
        """
        # Default implementation - can be overridden for efficiency
        return len(self.list())


class DatabaseStorageBase(StorageBase[T]):
    """
    Base class for database storage implementations.

    Use for structured, relational data:
    - User accounts
    - Chat sessions
    - Document metadata
    - Upload records

    Implementations:
    - PostgreSQLStorage (production)
    - SQLiteStorage (testing)
    """

    @abstractmethod
    def query(self, filters: dict[str, Any]) -> List[T]:
        """
        Query entities with filters.

        Args:
            filters: Dictionary of field:value pairs to filter by

        Returns:
            List of matching entities
        """
        raise NotImplementedError("Database storage must implement query()")

    @abstractmethod
    def bulk_create(self, entities: List[T]) -> List[str]:
        """
        Create multiple entities in a single transaction.

        Args:
            entities: List of entities to create

        Returns:
            List of created entity IDs
        """
        raise NotImplementedError("Database storage must implement bulk_create()")


class FileStorageBase(StorageBase[bytes]):
    """
    Base class for file storage implementations.

    Use for unstructured, binary data:
    - Uploaded documents (PDF, DOCX, TXT)
    - Extracted text files
    - Vector index files (FAISS)

    Implementations:
    - LocalFileStorage (development, single-server)
    - S3Storage (production, cloud)
    - MinIOStorage (production, self-hosted)
    """

    @abstractmethod
    def upload(
        self,
        file_content: bytes,
        destination_path: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Upload file content to storage.

        Args:
            file_content: The raw file bytes
            destination_path: Where to store the file
            metadata: Optional metadata tags

        Returns:
            The storage path/key of the uploaded file
        """
        raise NotImplementedError("File storage must implement upload()")

    @abstractmethod
    def download(self, file_path: str) -> Optional[bytes]:
        """
        Download file content from storage.

        Args:
            file_path: The storage path/key

        Returns:
            The file bytes if found, None otherwise
        """
        raise NotImplementedError("File storage must implement download()")

    @abstractmethod
    def get_url(self, file_path: str, expiry_seconds: int = 3600) -> Optional[str]:
        """
        Get a temporary URL for file access.

        Args:
            file_path: The storage path/key
            expiry_seconds: How long the URL should be valid

        Returns:
            Signed URL if supported, None otherwise
        """
        raise NotImplementedError("File storage must implement get_url()")

    @abstractmethod
    def list_files(self, prefix: Optional[str] = None) -> List[str]:
        """
        List files in storage.

        Args:
            prefix: Optional path prefix to filter by

        Returns:
            List of file paths
        """
        raise NotImplementedError("File storage must implement list_files()")

    # Override base methods with file-specific signatures
    def create(self, entity: bytes, entity_id: Optional[str] = None) -> str:
        """Create file - delegates to upload()"""
        if entity_id is None:
            raise ValueError("File storage requires explicit file path")
        return self.upload(entity, entity_id)

    def get(self, entity_id: str) -> Optional[bytes]:
        """Get file - delegates to download()"""
        return self.download(entity_id)

    def update(self, entity_id: str, entity: bytes) -> Optional[bytes]:
        """Update file - re-upload with same path"""
        self.upload(entity, entity_id)
        return entity

    def delete(self, entity_id: str) -> bool:
        """Delete file - must be implemented by subclass"""
        raise NotImplementedError("File storage must implement delete()")

    def exists(self, entity_id: str) -> bool:
        """Check if file exists"""
        return self.download(entity_id) is not None

    def list(self, entity_ids: Optional[List[str]] = None) -> List[bytes]:
        """List files - not typically used for file storage"""
        raise NotImplementedError("Use list_files() instead for file storage")
