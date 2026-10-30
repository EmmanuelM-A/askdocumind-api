"""
Integration tests for ChatSessionService against a real database and S3 bucket.

The service's repositories use the rolled-back test session. Deleting a chat
session opens its own session through the manager and commits, so the delete
tests seed committed data instead and check it from a fresh session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import status
from sqlalchemy import func, select

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_message_repository_impl import (
    ChatMessageRepositoryImpl,
)
from src.chat_session.repository.chat_session_repository_impl import (
    ChatSessionRepositoryImpl,
)
from src.chat_session.schemas.chat_session import CreateChatSession
from src.chat_session.services.chat_session_service import ChatSessionService
from src.config.configs import settings
from src.exceptions import object_storage_error
from src.exceptions.base import ApiException
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.uploads.models.document import Document

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_NEW_CHAT = CreateChatSession(title="New chat")


@pytest.fixture
def service(session, manager, object_storage):
    return ChatSessionService(
        user_repository=UserRepositoryImpl(session),
        chat_session_repository=ChatSessionRepositoryImpl(session),
        chat_message_repository=ChatMessageRepositoryImpl(session),
        object_storage=object_storage,
        session_manager=manager,
    )


async def _user(session):
    user = User()
    session.add(user)
    await session.flush()
    return user.id


async def _chat(session, user_id, created_at=_BASE_TIME):
    chat = ChatSession(user_id=user_id, title="existing", created_at=created_at)
    session.add(chat)
    await session.flush()
    return chat.id


async def _message(session, chat_session_id, content, created_at):
    message = ChatMessage(
        chat_session_id=chat_session_id,
        role=ChatMessageRole.USER,
        content=content,
        sources=["notes.txt"],
        created_at=created_at,
    )
    session.add(message)
    await session.flush()
    return message.id


async def _chat_count(session, user_id):
    statement = select(func.count()).where(ChatSession.user_id == user_id)
    return (await session.execute(statement)).scalar_one()


async def _committed_rows(manager, chat_session_id):
    """Count the chat session's rows in each table, from a fresh session."""
    async with manager.get_session() as session:
        return {
            model.__tablename__: (
                await session.execute(
                    select(func.count())
                    .select_from(model)
                    .where(
                        (model.id if model is ChatSession else model.chat_session_id)
                        == chat_session_id
                    )
                )
            ).scalar_one()
            for model in (ChatSession, ChatMessage, Document, ChunkEmbedding)
        }


def _all_rows_exist(rows):
    return all(count == 1 for count in rows.values())


def _no_rows_exist(rows):
    return all(count == 0 for count in rows.values())


class TestCreateNewChatSession:
    async def test_creates_and_returns_the_chat_session(self, service, session):
        user_id = await _user(session)

        created = await service.create_new_chat_session(user_id, _NEW_CHAT)

        stored = await session.get(ChatSession, created.id)
        assert stored is not None
        assert stored.user_id == user_id
        assert created.title == "New chat"
        assert created.created_at == stored.created_at.isoformat()

    async def test_unknown_user_raises_not_found(self, service):
        with pytest.raises(ApiException) as exc:
            await service.create_new_chat_session(uuid.uuid4(), _NEW_CHAT)

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_rejects_a_user_at_the_chat_limit(
        self, service, session, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 2)
        user_id = await _user(session)
        await _chat(session, user_id)
        await _chat(session, user_id)

        with pytest.raises(ApiException) as exc:
            await service.create_new_chat_session(user_id, _NEW_CHAT)

        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert await _chat_count(session, user_id) == 2

    async def test_other_users_chat_sessions_do_not_count_towards_the_limit(
        self, service, session, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 1)
        await _chat(session, await _user(session))
        user_id = await _user(session)

        await service.create_new_chat_session(user_id, _NEW_CHAT)

        assert await _chat_count(session, user_id) == 1


class TestInitializeChatSession:
    async def test_creates_a_chat_session_when_the_user_has_none(
        self, service, session
    ):
        user_id = await _user(session)

        initialized = await service.initialize_chat_session(user_id, _NEW_CHAT)

        assert initialized.title == "New chat"
        assert await _chat_count(session, user_id) == 1

    async def test_returns_the_latest_chat_session_without_creating_one(
        self, service, session
    ):
        user_id = await _user(session)
        await _chat(session, user_id, created_at=_BASE_TIME)
        latest_id = await _chat(session, user_id, _BASE_TIME + timedelta(hours=1))

        initialized = await service.initialize_chat_session(user_id, _NEW_CHAT)

        assert initialized.id == latest_id
        assert await _chat_count(session, user_id) == 2

    async def test_unknown_user_raises_not_found(self, service):
        with pytest.raises(ApiException) as exc:
            await service.initialize_chat_session(uuid.uuid4(), _NEW_CHAT)

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND


class TestGetChatSession:
    async def test_returns_the_owners_chat_session(self, service, session):
        user_id = await _user(session)
        chat_session_id = await _chat(session, user_id)

        found = await service.get_chat_session(user_id, chat_session_id)

        assert found.id == chat_session_id
        assert found.title == "existing"

    async def test_unknown_chat_session_raises_not_found(self, service, session):
        with pytest.raises(ApiException) as exc:
            await service.get_chat_session(await _user(session), uuid.uuid4())

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_another_users_chat_session_is_forbidden(self, service, session):
        chat_session_id = await _chat(session, await _user(session))

        with pytest.raises(ApiException) as exc:
            await service.get_chat_session(await _user(session), chat_session_id)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


class TestGetChatSessionMessages:
    async def test_returns_the_messages_oldest_first(self, service, session):
        user_id = await _user(session)
        chat_session_id = await _chat(session, user_id)
        later = await _message(session, chat_session_id, "second", _BASE_TIME)
        earlier = await _message(
            session, chat_session_id, "first", _BASE_TIME - timedelta(minutes=1)
        )

        messages = await service.get_chat_session_messages(user_id, chat_session_id)

        assert [m.id for m in messages] == [earlier, later]
        assert messages[0].content == "first"
        assert messages[0].role == "user"
        assert messages[0].sources == ["notes.txt"]

    async def test_excludes_the_users_other_chat_sessions(self, service, session):
        user_id = await _user(session)
        chat_session_id = await _chat(session, user_id)
        other_chat_session_id = await _chat(session, user_id)
        wanted = await _message(session, chat_session_id, "here", _BASE_TIME)
        await _message(session, other_chat_session_id, "elsewhere", _BASE_TIME)

        messages = await service.get_chat_session_messages(user_id, chat_session_id)

        assert [m.id for m in messages] == [wanted]

    async def test_chat_session_without_messages_returns_empty_list(
        self, service, session
    ):
        user_id = await _user(session)
        chat_session_id = await _chat(session, user_id)

        assert await service.get_chat_session_messages(user_id, chat_session_id) == []

    async def test_another_users_chat_session_is_forbidden(self, service, session):
        chat_session_id = await _chat(session, await _user(session))

        with pytest.raises(ApiException) as exc:
            await service.get_chat_session_messages(
                await _user(session), chat_session_id
            )

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


class TestDeleteChatSession:
    async def test_removes_the_rows_and_stored_files(
        self, service, manager, object_storage, seed_chat
    ):
        chat = await seed_chat()

        await service.delete_chat_session(chat.user_id, chat.chat_session_id)

        assert _no_rows_exist(await _committed_rows(manager, chat.chat_session_id))
        assert not object_storage.exists(chat.object_key)

    async def test_leaves_the_users_other_chat_sessions_alone(
        self, service, manager, object_storage, seed_chat
    ):
        deleted = await seed_chat()
        kept = await seed_chat(user_id=deleted.user_id)

        await service.delete_chat_session(deleted.user_id, deleted.chat_session_id)

        assert _all_rows_exist(await _committed_rows(manager, kept.chat_session_id))
        assert object_storage.exists(kept.object_key)

    async def test_another_users_chat_session_is_forbidden_and_kept(
        self, service, session, manager, object_storage, seed_chat
    ):
        chat = await seed_chat()

        with pytest.raises(ApiException) as exc:
            await service.delete_chat_session(
                await _user(session), chat.chat_session_id
            )

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert _all_rows_exist(await _committed_rows(manager, chat.chat_session_id))
        assert object_storage.exists(chat.object_key)

    async def test_storage_failure_keeps_the_rows(
        self, service, manager, object_storage, seed_chat
    ):
        chat = await seed_chat()
        failure = object_storage_error(message="S3 is down")

        with (
            patch.object(object_storage, "delete_prefix", side_effect=failure),
            pytest.raises(ApiException) as exc,
        ):
            await service.delete_chat_session(chat.user_id, chat.chat_session_id)

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert _all_rows_exist(await _committed_rows(manager, chat.chat_session_id))

    async def test_second_cleanup_failure_is_logged_not_raised(
        self, service, manager, object_storage, seed_chat, caplog
    ):
        chat = await seed_chat()
        real_delete_prefix = object_storage.delete_prefix
        calls = iter([real_delete_prefix, object_storage_error(message="S3 is down")])

        def delete_prefix(prefix):
            step = next(calls)
            if isinstance(step, Exception):
                raise step
            return step(prefix)

        with patch.object(object_storage, "delete_prefix", side_effect=delete_prefix):
            await service.delete_chat_session(chat.user_id, chat.chat_session_id)

        assert _no_rows_exist(await _committed_rows(manager, chat.chat_session_id))
        assert not object_storage.exists(chat.object_key)
        assert "Second file cleanup failed" in caplog.text
