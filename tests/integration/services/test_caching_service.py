"""
Unit tests for caching service implementations.
Any implementation of CachingService should pass this suite.
"""

import time
import uuid

import pytest

from src.api.services.caching.redis_cache import RedisCache


@pytest.fixture
def cache():
    """
    Provides a fresh cache instance per test using a unique namespace.
    Uses RedisCache for testing without requiring Redis to be running.
    """
    namespace = f"test:{uuid.uuid4().hex}"
    c = RedisCache(namespace=namespace)
    yield c
    c.clear()
    c.close()


# ==================== BASIC SET / GET ====================


def test_successful_cache_set_operation(cache):
    result = cache.set("key1", "value1")
    assert result is True


def test_cache_hit(cache):
    cache.set("key1", "value1")
    value = cache.get("key1")
    assert value == "value1"


def test_cache_miss(cache):
    value = cache.get("missing_key")
    assert value is None


# ==================== TTL BEHAVIOR ====================


def test_cache_set_with_ttl_expires(cache):
    cache.set("ttl_key", "temp", ttl=1)
    time.sleep(2)
    assert cache.get("ttl_key") is None


# ==================== DELETE ====================


def test_successful_cache_delete(cache):
    cache.set("key1", "value1")
    deleted = cache.delete("key1")
    assert deleted == "key1"
    assert cache.get("key1") is None


def test_unsuccessful_cache_delete(cache):
    deleted = cache.delete("missing_key")
    assert deleted is None


# ==================== EXISTS ====================


def test_cache_exists(cache):
    cache.set("key1", "value1")
    assert cache.exists("key1") is True
    assert cache.exists("missing_key") is False


# ==================== CLEAR ====================


def test_successful_cache_clear(cache):
    cache.set("key1", "value1")
    cache.set("key2", "value2")

    cleared = cache.clear()
    assert cleared is True
    assert cache.get("key1") is None
    assert cache.get("key2") is None


# ==================== NAMESPACE ====================


def test_cache_clear_namespace(cache):
    cache.set("user:1", "a")
    cache.set("user:2", "b")
    cache.set("session:1", "c")

    cleared = cache.clear_namespace("user:")
    assert cleared is True

    assert cache.get("user:1") is None
    assert cache.get("user:2") is None
    assert cache.get("session:1") == "c"


# ==================== CLOSE ====================


def test_cache_close(cache):
    closed = cache.close()
    assert closed is True
