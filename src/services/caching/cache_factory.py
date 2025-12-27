"""
Cache factory for creating different types of caches throughout the application.
"""

from src.logger.base_logger import BaseLogger
from src.services.caching.caching_service import CachingService
from src.services.caching.redis_cache import RedisCache
from src.config.configs import settings

logger = BaseLogger(__name__)


class CacheFactory:
    """Factory for creating and managing cache instances."""

    _instances: dict[str, CachingService] = {}

    @classmethod
    def get_cache(cls, namespace: str) -> CachingService:
        """
        Get or create a cache instance for a namespace.

        Args:
            namespace: Cache namespace (e.g., 'api_responses', 'embeddings', 'queries')

        Returns:
            RedisCache instance
        """
        cache_key = f"{namespace}:{settings.cache.REDIS_DB}"

        if cache_key not in cls._instances:
            cls._instances[cache_key] = RedisCache(
                namespace=namespace
            )  # NOTE: REDIS CACHE USED
            logger.info(f"Creating new cache instance for namespace: {namespace}")

        return cls._instances[cache_key]

    @classmethod
    def close_all(cls) -> None:
        """Close all cache connections."""

        for cache_key, cache in cls._instances.items():
            cache.close()
            logger.info(f"Closed cache:  {cache_key}")

        cls._instances.clear()
