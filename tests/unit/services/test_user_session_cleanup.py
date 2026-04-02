"""Unit tests for user-session cleanup jobs."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.api.services.user_session_cleanup import (
    UserSessionCleanupService,
    run_user_session_cleanup_scheduler,
)
from src.database.models import ChatSession, User


@pytest.mark.asyncio
async def test_cleanup_expired_user_sessions_removes_related_resources(monkeypatch: pytest.MonkeyPatch):
    user_id = uuid4()
    chat_id_1 = uuid4()
    chat_id_2 = uuid4()

    expired_user = User(id=user_id, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1))
    chat_sessions = [
        ChatSession(id=chat_id_1, user_id=user_id),
        ChatSession(id=chat_id_2, user_id=user_id),
    ]

    user_repo = Mock()
    user_repo.delete = AsyncMock(return_value=True)

    chat_session_repo = Mock()
    chat_session_repo.list_by = AsyncMock(return_value=chat_sessions)

    storage_service = Mock()
    storage_service.delete_all = Mock(return_value=1)

    chatbot = Mock()
    chatbot.chat_exists = Mock(side_effect=[True, False])
    chatbot.delete_chat = Mock()

    cache = Mock()
    cache.clear_namespace = Mock(return_value=False)
    monkeypatch.setattr(
        "src.api.services.user_session_cleanup.CacheFactory.get_cache",
        Mock(return_value=cache),
    )

    service = UserSessionCleanupService(
        db_connection=Mock(),
        user_repo=user_repo,
        chat_session_repo=chat_session_repo,
        storage_service=storage_service,
        chatbot=chatbot,
    )
    service._get_expired_users = AsyncMock(return_value=[expired_user])

    cleaned = await service.cleanup_expired_user_sessions(batch_size=10)

    assert cleaned == 1
    chat_session_repo.list_by.assert_awaited_once()
    storage_service.delete_all.assert_any_call(str(chat_id_1))
    storage_service.delete_all.assert_any_call(str(chat_id_2))
    chatbot.delete_chat.assert_called_once_with(str(chat_id_1))
    user_repo.delete.assert_awaited_once_with(user_id)
    assert cache.clear_namespace.call_count >= 3


@pytest.mark.asyncio
async def test_scheduler_runs_cleanup_once_and_stops():
    stop_event = __import__("asyncio").Event()
    cleanup_service = Mock()
    cleanup_service.run_scheduler = AsyncMock(return_value=None)

    await run_user_session_cleanup_scheduler(
        stop_event=stop_event,
        interval_minutes=1,
        batch_size=5,
        cleanup_service=cleanup_service,
    )

    cleanup_service.run_scheduler.assert_awaited_once_with(
        stop_event=stop_event,
        interval_minutes=1,
        batch_size=5,
    )


