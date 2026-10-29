"""
Unit tests for the per user chat session limit in
ChatSessionService.create_new_chat_session.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.database.models  # noqa: F401  registers every model for the mappers
from src.chat_session.schemas.chat_session import CreateChatSession
from src.chat_session.services.chat_session_service import ChatSessionService
from src.config.configs import settings
from src.exceptions.base import ApiException

pytestmark = pytest.mark.asyncio

USER_ID = uuid.uuid4()
LIMIT = settings.chat_session.MAX_CHATS_PER_USER


@pytest.fixture
def chat_session_repository():
    return AsyncMock()


@pytest.fixture
def service(chat_session_repository):
    user_repository = AsyncMock()
    user_repository.get_by_id.return_value = SimpleNamespace(id=USER_ID)

    return ChatSessionService(
        user_repository=user_repository,
        chat_session_repository=chat_session_repository,
        chat_message_repository=AsyncMock(),
        object_storage=MagicMock(),
        session_manager=MagicMock(),
    )


@pytest.mark.parametrize("existing", [LIMIT, LIMIT + 1], ids=["at-limit", "over-limit"])
async def test_create_is_rejected_when_user_has_max_chats(
    service, chat_session_repository, existing
):
    chat_session_repository.count.return_value = existing

    with pytest.raises(ApiException) as exc:
        await service.create_new_chat_session(USER_ID, CreateChatSession(title="t"))

    assert exc.value.error_code == "MAX_CHAT_SESSIONS_REACHED"
    chat_session_repository.count.assert_awaited_once_with(USER_ID)
    chat_session_repository.create.assert_not_awaited()


async def test_create_below_limit_is_stored(service, chat_session_repository):
    chat_session_repository.count.return_value = LIMIT - 1

    await service.create_new_chat_session(USER_ID, CreateChatSession(title="t"))

    chat_session_repository.create.assert_awaited_once()


async def test_limit_comes_from_settings(service, chat_session_repository, monkeypatch):
    monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 2)
    chat_session_repository.count.return_value = 2

    with pytest.raises(ApiException):
        await service.create_new_chat_session(USER_ID, CreateChatSession(title="t"))
