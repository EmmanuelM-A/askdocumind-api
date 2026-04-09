"""Unit tests for anonymous resource cleanup service."""

import asyncio
import importlib
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class _TxContext:
    def __init__(self, tx):
        self.tx = tx

    async def __aenter__(self):
        return self.tx

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _TxFactory:
    def __init__(self, txs):
        self._txs = iter(txs)

    def create(self):
        return _TxContext(next(self._txs))


@pytest.fixture
def cleanup_module(monkeypatch: pytest.MonkeyPatch):
    # Patch module-level dependencies before importing the module under test.
    import src.components.chatbot.chatbot_factory as chatbot_factory
    import src.database.repository as repository_pkg
    import src.database.repository.database_repository_factory as tx_factory_pkg
    import src.database.storage as storage_pkg

    monkeypatch.setattr(chatbot_factory, "get_chatbot", lambda: Mock())
    monkeypatch.setattr(repository_pkg, "get_database_repository", lambda _model: Mock())
    monkeypatch.setattr(tx_factory_pkg, "get_tx_factory", lambda: Mock())
    monkeypatch.setattr(storage_pkg, "get_storage_service", lambda: Mock())

    module = importlib.import_module("src.api.services.cleanup.cleanup_resources")
    return importlib.reload(module)


@pytest.mark.asyncio
async def test_get_expired_user_ids_returns_values_from_transaction(cleanup_module):
    tx = Mock()
    expected_ids = [uuid4(), uuid4()]
    tx.execute = AsyncMock(return_value=_Result(expected_ids))

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=Mock(),
        chat_repo=Mock(),
        tx_factory=_TxFactory([tx]),
        chatbot=Mock(),
        storage_service=Mock(),
    )

    result = await service._get_expired_user_ids(datetime(2026, 4, 9, 12, 0, 0))

    assert result == expected_ids
    tx.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_sessions_deletes_user_when_resources_are_cleared(cleanup_module):
    user_id = uuid4()
    tx = Mock()

    chat_repo = Mock()
    chat_repo.list_by = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])

    user_repo = Mock()
    user_repo.delete = AsyncMock(return_value=True)

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=user_repo,
        chat_repo=chat_repo,
        tx_factory=_TxFactory([tx]),
        chatbot=Mock(),
        storage_service=Mock(),
    )
    service._get_expired_user_ids = AsyncMock(return_value=[user_id])
    service._clear_additional_resources = Mock(return_value=True)
    service._clear_caches = Mock()

    deleted_count = await service._cleanup_expired_anonymous_user_sessions()

    assert deleted_count == 1
    chat_repo.list_by.assert_awaited_once()
    called_criteria = chat_repo.list_by.await_args.kwargs["criteria"]
    assert called_criteria.user_id == user_id
    assert chat_repo.list_by.await_args.kwargs["tx"] is tx
    user_repo.delete.assert_awaited_once_with(user_id, tx=tx)


@pytest.mark.asyncio
async def test_cleanup_sessions_skips_user_delete_when_resource_cleanup_fails(cleanup_module):
    user_id = uuid4()
    tx = Mock()

    chat_repo = Mock()
    chat_repo.list_by = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])

    user_repo = Mock()
    user_repo.delete = AsyncMock(return_value=True)

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=user_repo,
        chat_repo=chat_repo,
        tx_factory=_TxFactory([tx]),
        chatbot=Mock(),
        storage_service=Mock(),
    )
    service._get_expired_user_ids = AsyncMock(return_value=[user_id])
    service._clear_additional_resources = Mock(return_value=False)
    service._clear_caches = Mock()

    deleted_count = await service._cleanup_expired_anonymous_user_sessions()

    assert deleted_count == 0
    user_repo.delete.assert_not_awaited()
    service._clear_caches.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_sessions_continues_after_user_transaction_error(cleanup_module):
    user_1 = uuid4()
    user_2 = uuid4()
    tx_1 = Mock()
    tx_2 = Mock()

    chat_repo = Mock()
    chat_repo.list_by = AsyncMock(side_effect=[RuntimeError("boom"), []])

    user_repo = Mock()
    user_repo.delete = AsyncMock(return_value=True)

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=user_repo,
        chat_repo=chat_repo,
        tx_factory=_TxFactory([tx_1, tx_2]),
        chatbot=Mock(),
        storage_service=Mock(),
    )
    service._get_expired_user_ids = AsyncMock(return_value=[user_1, user_2])
    service._clear_additional_resources = Mock(return_value=True)
    service._clear_caches = Mock()

    deleted_count = await service._cleanup_expired_anonymous_user_sessions()

    assert deleted_count == 1
    user_repo.delete.assert_awaited_once_with(user_2, tx=tx_2)


def test_clear_caches_clears_each_namespace_per_chat_id(cleanup_module, monkeypatch):
    cache_sessions = Mock()
    cache_queries = Mock()
    cache_documents = Mock()
    cache_by_namespace = {
        cleanup_module.CacheNamespace.SESSIONS: cache_sessions,
        cleanup_module.CacheNamespace.QUERIES: cache_queries,
        cleanup_module.CacheNamespace.DOCUMENTS: cache_documents,
    }

    monkeypatch.setattr(
        cleanup_module.CacheFactory,
        "get_cache",
        lambda namespace: cache_by_namespace[namespace],
    )

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=Mock(),
        chat_repo=Mock(),
        tx_factory=Mock(),
        chatbot=Mock(),
        storage_service=Mock(),
    )

    service._clear_caches(["chat-1", "chat-2"])

    assert cache_sessions.clear_namespace.call_count == 2
    assert cache_queries.clear_namespace.call_count == 2
    assert cache_documents.clear_namespace.call_count == 2


def test_clear_additional_resources_returns_false_when_any_cleanup_step_fails(cleanup_module):
    chatbot = Mock()
    chatbot.chat_exists.side_effect = [True, True]
    chatbot.delete_chat.side_effect = [None, RuntimeError("vector error")]

    storage = Mock()
    storage.delete_all.side_effect = [None, RuntimeError("storage error")]

    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=Mock(),
        chat_repo=Mock(),
        tx_factory=Mock(),
        chatbot=chatbot,
        storage_service=storage,
    )

    result = service._clear_additional_resources(["chat-1", "chat-2"])

    assert result is False
    assert storage.delete_all.call_count == 2
    assert chatbot.chat_exists.call_count == 2
    assert chatbot.delete_chat.call_count == 2


@pytest.mark.asyncio
async def test_run_scheduler_stops_when_event_is_set(cleanup_module):
    service = cleanup_module.CleanupAnonymousUserResources(
        user_repo=Mock(),
        chat_repo=Mock(),
        tx_factory=Mock(),
        chatbot=Mock(),
        storage_service=Mock(),
    )

    stop_event = asyncio.Event()
    calls = {"count": 0}

    async def _cleanup_once():
        calls["count"] += 1
        stop_event.set()

    service._cleanup_expired_anonymous_user_sessions = _cleanup_once

    await service.run_scheduler(stop_event=stop_event, interval_minutes=1)

    assert calls["count"] == 1

