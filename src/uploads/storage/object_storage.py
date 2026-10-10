"""
Abstract object storage interface along with utility functions.
"""

from abc import ABC, abstractmethod

from exceptions import unprocessable_content_error


class ObjectStorage(ABC):
    """Abstract interface for all object storage services."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> None:
        """
        Store data under the specified key. If the key already exists, it
        will be overwritten.
        """
        raise NotImplementedError(
            "The method 'save' must be implemented by its subclasses."
        )

    @abstractmethod
    def load(self, key: str) -> bytes | None:
        """Return the bytes for key, or None when the key does not exist."""
        raise NotImplementedError(
            "The method 'load' must be implemented by its subclasses."
        )

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete key. Deleting a missing key is not an error."""
        raise NotImplementedError(
            "The method 'delete' must be implemented by its subclasses."
        )

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True when key exists."""
        raise NotImplementedError(
            "The method 'exists' must be implemented by its subclasses."
        )

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """
        Delete every object under the folder prefix and return the count.
        The prefix must not be empty.
        """
        raise NotImplementedError(
            "The method 'delete_prefix' must be implemented by its subclasses."
        )

    @abstractmethod
    def presigned_url(self, key: str, expires_in_secs: int) -> str:
        """
        Return a presigned URL for the object with the given key.
        The URL will expire in expires_in seconds.
        """
        raise NotImplementedError(
            "The method 'presigned_url' must be implemented by its subclasses."
        )


def validate_key(key: str) -> str:
    """
    Reject keys with traversal parts, empty parts, or odd characters.
    """
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise unprocessable_content_error(
            message="The storage key provided is invalid",
            error_code="INVALID_STORAGE_KEY",
        )

    if any(part in ("", ".", "..") for part in key.split("/")):
        raise unprocessable_content_error(
            message="The storage key provided is invalid",
            error_code="INVALID_STORAGE_KEY",
        )

    return key


def normalize_prefix(prefix: str) -> str:
    """
    Validate a folder prefix and remove the trailing slash.
    """
    return validate_key(prefix.rstrip("/"))
