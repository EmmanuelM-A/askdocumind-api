"""
Abstract storage service interface.

Defines the minimal file/object-storage contract used by the application:
- save: store bytes at a key.
- load: retrieve bytes for a key, or return None if not found.
- delete: remove a stored object and optionally return a confirmation or None.
- exists: check whether a key exists.

Concrete implementations should handle key normalization, security concerns
(e.g. path traversal), and any storage-specific behavior (local FS, cloud, etc.).
"""

from abc import ABC, abstractmethod
from typing import Optional


class StorageService(ABC):
    """
    Abstract base class for storage backends.

    Implementations should provide non-blocking or blocking IO as appropriate
    for the application. Method semantics:

    - save(key, data): Persist `data` bytes under `key`. Overwrite behavior
      should be documented by the implementation.
    - load(key): Return the stored bytes for `key`, or `None` if the key is
      not present or inaccessible.
    - delete(key): Remove the stored item for `key`. Return an optional string
      (e.g. confirmation or error message) or `None`.
    - exists(key): Return `True` if `key` is present, otherwise `False`.
    """

    @abstractmethod
    def save(self, key: str, data: bytes) -> None:
        """
        Save `data` under `key`.

        :param key: Storage key (implementation-defined format, e.g. relative path).
        :param data: Raw bytes to persist.
        :return: None
        """
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str) -> Optional[bytes]:
        """
        Load and return bytes stored at `key`.

        :param key: Storage key to load.
        :return: Bytes if the key exists, otherwise `None`.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> Optional[str]:
        """
        Delete the object at `key`.

        :param key: Storage key to delete.
        :return: Optional confirmation string or `None`.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check whether `key` exists in storage.

        :param key: Storage key to check.
        :return: True if present, False otherwise.
        """
        raise NotImplementedError
