"""
Integration tests for ChatSessionRepositoryImpl against a real database.

Everything runs inside the rolled-back test session. Postgres gives every row
in one transaction the same now(), so tests that depend on order set
created_at themselves.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_session_repository_impl import (
    ChatSessionRepositoryImpl,
)
from src.database.utils import Pagination
from src.exceptions.base import ApiException
from src.uploads.models.document import Document

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def repo(session):
    return ChatSessionRepositoryImpl(session)


async def _user(session):
    user = User()
    session.add(user)
    await session.flush()
    return user.id


async def _chats(repo, user_id, count, created_at=None):
    """Create chats an hour apart, oldest first, or all at created_at."""
    chats = []
    for i in range(count):
        chat = ChatSession(
            user_id=user_id,
            title=f"chat {i}",
            created_at=created_at or _BASE_TIME + timedelta(hours=i),
        )
        chats.append(await repo.create(chat))
    return chats


async def _row_count(session, model, chat_session_id):
    column = model.id if model is ChatSession else model.chat_session_id
    statement = select(func.count()).select_from(model).where(column == chat_session_id)
    return (await session.execute(statement)).scalar_one()


class TestCreate:
    async def test_persists_with_generated_id_and_timestamp(self, repo, session):
        user_id = await _user(session)

        chat = await repo.create(ChatSession(user_id=user_id, title="first"))

        assert isinstance(chat.id, uuid.UUID)
        assert chat.created_at is not None
        assert await _row_count(session, ChatSession, chat.id) == 1

    async def test_unknown_user_raises_database_error(self, repo):
        with pytest.raises(ApiException) as exc:
            await repo.create(ChatSession(user_id=uuid.uuid4(), title="orphan"))

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetById:
    async def test_returns_the_chat_session(self, repo, session):
        [chat] = await _chats(repo, await _user(session), 1)

        found = await repo.get_by_id(chat.id)

        assert found is not None
        assert found.id == chat.id
        assert found.title == chat.title

    async def test_unknown_id_returns_none(self, repo):
        assert await repo.get_by_id(uuid.uuid4()) is None


class TestGetByUserId:
    async def test_returns_the_most_recent_chat_session(self, repo, session):
        user_id = await _user(session)
        chats = await _chats(repo, user_id, 3)

        found = await repo.get_by_user_id(user_id)

        assert found is not None
        assert found.id == chats[-1].id

    async def test_user_without_chat_sessions_returns_none(self, repo, session):
        assert await repo.get_by_user_id(await _user(session)) is None


class TestListByOwner:
    async def test_returns_only_the_owners_chat_sessions_newest_first(
        self, repo, session
    ):
        user_id = await _user(session)
        chats = await _chats(repo, user_id, 3)
        await _chats(repo, await _user(session), 2)

        listed = await repo.list_by_owner(user_id)

        assert [chat.id for chat in listed] == [chat.id for chat in reversed(chats)]

    async def test_breaks_created_at_ties_by_id_descending(self, repo, session):
        user_id = await _user(session)
        # Enough rows that an unordered result can't match by chance
        chats = await _chats(repo, user_id, 10, created_at=_BASE_TIME)

        listed = await repo.list_by_owner(user_id)

        assert [chat.id for chat in listed] == sorted(
            (chat.id for chat in chats), reverse=True
        )

    async def test_user_without_chat_sessions_returns_empty_list(self, repo, session):
        assert await repo.list_by_owner(await _user(session)) == []

    async def test_database_failure_raises_retrieval_error(self, repo, session):
        failing = AsyncMock(side_effect=SQLAlchemyError("boom"))

        with patch.object(session, "execute", failing), pytest.raises(
            ApiException
        ) as exc:
            await repo.list_by_owner(uuid.uuid4())

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestListByOwnerPaginated:
    async def test_returns_the_requested_page_and_total(self, repo, session):
        user_id = await _user(session)
        newest_first = list(reversed(await _chats(repo, user_id, 5)))

        page = await repo.list_by_owner_paginated(user_id, Pagination(page=2, limit=2))

        assert [chat.id for chat in page.items] == [c.id for c in newest_first[2:4]]
        assert page.total == 5
        assert page.pages == 3

    async def test_page_past_the_end_is_empty_but_keeps_the_total(self, repo, session):
        user_id = await _user(session)
        await _chats(repo, user_id, 3)

        page = await repo.list_by_owner_paginated(user_id, Pagination(page=4, limit=2))

        assert page.items == []
        assert page.total == 3


class TestCount:
    async def test_counts_only_the_users_chat_sessions(self, repo, session):
        user_id = await _user(session)
        await _chats(repo, user_id, 3)
        await _chats(repo, await _user(session), 2)

        assert await repo.count(user_id) == 3

    async def test_user_without_chat_sessions_counts_zero(self, repo, session):
        assert await repo.count(await _user(session)) == 0


class TestDelete:
    async def test_removes_the_chat_session_and_cascades_to_children(
        self, repo, session
    ):
        [chat] = await _chats(repo, await _user(session), 1)
        session.add_all(
            [
                ChatMessage(
                    chat_session_id=chat.id,
                    role=ChatMessageRole.USER,
                    content="hi",
                    sources=[],
                ),
                Document(
                    chat_session_id=chat.id,
                    original_filename="notes.txt",
                    object_key=f"{chat.id}/{uuid.uuid4()}",
                    content_type="text/plain",
                    size_bytes=1,
                    checksum="0" * 64,
                ),
            ]
        )
        await session.flush()

        await repo.delete(chat.id)

        assert await _row_count(session, ChatSession, chat.id) == 0
        assert await _row_count(session, ChatMessage, chat.id) == 0
        assert await _row_count(session, Document, chat.id) == 0

    async def test_unknown_id_raises_not_found(self, repo):
        with pytest.raises(ApiException) as exc:
            await repo.delete(uuid.uuid4())

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteMany:
    async def test_deletes_only_the_listed_chat_sessions(self, repo, session):
        user_id = await _user(session)
        first, second, kept = await _chats(repo, user_id, 3)

        deleted = await repo.delete_many([first.id, second.id, uuid.uuid4()])

        assert deleted == 2
        assert [chat.id for chat in await repo.list_by_owner(user_id)] == [kept.id]

    async def test_empty_list_returns_zero_without_querying(self, repo, session):
        with patch.object(session, "execute", AsyncMock()) as execute:
            assert await repo.delete_many([]) == 0

        execute.assert_not_awaited()
