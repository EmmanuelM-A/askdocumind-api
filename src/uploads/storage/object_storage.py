"""
Abstract object storage interface.
"""

from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Abstract interface for all object storage services."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> None:
        """Store data under key. Overwrite any existing object."""

    @abstractmethod
    def load(self, key: str) -> bytes | None:
        """Return the bytes for key, or None when the key does not exist."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete key. Deleting a missing key is not an error."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True when key exists."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """
        Delete every object under the folder prefix and return the count.
        The prefix must not be empty.
        """
