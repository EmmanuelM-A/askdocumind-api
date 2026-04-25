"""
Factory method to retrieve (or create) the current storage service instance.
This allows for easy swapping of storage implementations in the future without
changing the service layer code.
"""

from typing import Optional

from src.database.storage.storage_service import StorageService
from src.database.storage.s3_storage_service import S3StorageService

_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Factory method to get a singleton instance of the current StorageService."""

    global _storage_service

    if _storage_service is None:
        _storage_service = S3StorageService()

    return _storage_service
