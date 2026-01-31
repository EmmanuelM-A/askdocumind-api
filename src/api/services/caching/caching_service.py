"""
Defines an abstract base class for caching services.
All caching service implementations should inherit from this class and
implement the defined methods.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class CachingService(ABC):
    """
    Abstract base class for caching services.
    """

    @abstractmethod
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache a value with optional TTL.

        Args:
            key (str): The cache key.
            value (Any): The value to cache.
            ttl (Optional[int]): Time-to-live in seconds.

        Returns:
            bool: True if the value was cached successfully, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value.

        Args:
            key (str): The cache key.

        Returns:
            Optional[Any]: The cached value or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> Optional[str]:
        """
        Delete a cache entry.

        Args:
            key (str): The cache key to delete.

        Returns:
            str: Deleted key or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> bool:
        """
        Clear the entire cache.

        Returns:
            bool: True if the cache was cleared successfully, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self) -> bool:
        """
        Close the caching service connection.

        Returns:
            bool: True if the connection was closed successfully, False otherwise.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if a key exists.

        Args:
            key (str): The cache key to check.

        Returns:
            bool: True if the key exists, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def clear_namespace(self, prefix: str) -> bool:
        """
        Clear all keys matching a prefix (namespace).

        Args:
            prefix (str): The prefix to match keys.

        Returns:
            bool: True if the namespace was cleared successfully, False otherwise.
        """
        raise NotImplementedError
