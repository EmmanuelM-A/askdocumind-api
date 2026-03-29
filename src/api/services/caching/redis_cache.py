"""
Redis-based caching service.
Used for caching application data including embeddings, API responses, etc.
"""

import json
import pickle
from typing import Any, Optional

import redis

from src.config.configs import settings
from src.config.constants import CacheNamespace
from src.logger.base_logger import BaseLogger
from src.errors.custom_exceptions import server_error
from src.api.services.caching.caching_service import CachingService

logger = BaseLogger(__name__)


class RedisCache(CachingService):
    """
    Handles caching using Redis as the backend.
    """

    def __init__(self, namespace: str = CacheNamespace.DEFAULT):
        """
        Initialize Redis cache client

        Args:
            namespace (str): Prefix for cache keys to avoid collisions.
        """

        self.namespace = namespace

        try:
            self.client = redis.Redis(
                host=settings.cache.REDIS_HOST,
                port=settings.cache.REDIS_PORT,
                db=settings.cache.REDIS_DB,
                decode_responses=False,  # important for pickle
            )

            # Test connection
            self.client.ping()
            logger.info("Redis cache connected successfully")

        except Exception as e:
            self.client = None
            raise server_error(
                message="Failed to connect to Redis!",
                error_code="REDIS_CONNECTION_ERROR",
                stack_trace=str(e),
            )

    # ========================== PUBLIC API ==========================

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = settings.cache.REDIS_TTL_SECONDS,
    ) -> bool:
        try:
            payload = self._serialize(value)
            self.client.set(
                name=self._key(key),
                value=payload,
                ex=ttl,
            )

            return True
        except Exception as e:
            logger.error(f"Failed to set cache key '{self._key(key)}': {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        try:
            payload = self.client.get(self._key(key))
            if payload is None:
                return None
            return self._deserialize(payload)
        except Exception as e:
            logger.error(f"Failed to get cache key '{self._key(key)}': {e}")
            return None

    def delete(self, key: str) -> Optional[str]:
        try:
            deleted = self.client.delete(self._key(key))

            if deleted == 0:
                return None

            return key
        except Exception as e:
            logger.error(f"Failed to delete cache key '{key}': {e}")
            return None

    def clear(self) -> bool:
        try:
            self.client.flushdb()
            logger.info("Redis cache cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
            return False

    def close(self) -> bool:
        if self.client:
            self.client.close()
            logger.info("Redis cache connection closed")
            return True

        logger.warning("Redis cache client was not initialized")
        return False

    def exists(self, key: str) -> bool:
        try:
            return bool(self.client.exists(self._key(key)))
        except Exception:
            return False

    def clear_namespace(self, prefix: str) -> bool:
        try:
            keys = self.client.keys(f"{self._key(prefix)}*")
            if keys:
                self.client.delete(*keys)
                logger.debug(f"Cleared {len(keys)} keys from namespace '{prefix}'")
                return True

            logger.info(f"No keys found for namespace '{prefix}' to clear")
            return False
        except Exception as e:
            logger.error(f"Failed to clear namespace '{prefix}': {e}")
            return False

    # ========================== HELPER METHODS ==========================

    def _key(self, key: str) -> str:
        """Apply namespace prefix."""
        return f"{self.namespace}:{key}"

    @staticmethod
    def _serialize(value: Any) -> bytes:
        """
        Serialize value for Redis storage.
        """

        try:
            # Try JSON first (human-readable, portable)
            return json.dumps(value).encode("utf-8")
        except (TypeError, ValueError):
            # Fallback to pickle
            return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _deserialize(payload: bytes) -> Any:
        """
        Deserialize Redis payload.
        """

        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return pickle.loads(payload)
