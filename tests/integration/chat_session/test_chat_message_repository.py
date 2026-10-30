"""
Integration tests for ChatMessageRepositoryImpl against a real database.

Everything runs inside the rolled-back test session. Postgres gives every row
in one transaction the same now(), so tests that depend on order set
created_at themselves.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_message_repository import (
    ChatMessageSearchFilter,
)
from src.chat_session.repository.chat_message_repository_impl import (
    ChatMessageRepositoryImpl,
)
from src.database.utils import Pagination
from src.exceptions.base import ApiException

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_USER = ChatMessageRole.USER
_ASSISTANT = ChatMessageRole.ASSISTANT


@pytest.fixture
def repo(session):
    return ChatMessageRepositoryImpl(session)


async def _user(session):
    user = User()
    session.add(user)
    await session.flush()
    return user.id


async def _chat(session, user_id):
    chat_session = ChatSession(user_id=user_id, title="test")
    session.add(chat_session)
    await session.flush()
    return chat_session.id


async def _message(repo, chat_session_id, minute=0, role=_USER, sources=()):
    message = ChatMessage(
        chat_session_id=chat_session_id,
        role=role,
        content=f"message at minute {minute}",
        sources=list(sources),
        created_at=_BASE_TIME + timedelta(minutes=minute),
    )
    return (await repo.create(message)).id


def _ids(messages):
    return [message.id for message in messages]


class TestCreate:
    async def test_persists_the_message_with_generated_defaults(self, repo, session):
        chat_id = await _chat(session, await _user(session))

        message = await repo.create(
            ChatMessage(
                chat_session_id=chat_id,
                role=_ASSISTANT,
                content="The answer.",
                sources=["a.pdf", "Moon facts"],
            )
        )

        assert isinstance(message.id, uuid.UUID)
        assert message.created_at is not None
        stored = await session.execute(
            select(ChatMessage.role, ChatMessage.content, ChatMessage.sources).where(
                ChatMessage.id == message.id
            )
        )
        assert stored.one() == (_ASSISTANT, "The answer.", ["a.pdf", "Moon facts"])

    async def test_unknown_chat_session_raises_a_server_error(self, repo):
        message = ChatMessage(
            chat_session_id=uuid.uuid4(), role=_USER, content="orphan", sources=[]
        )

        with pytest.raises(ApiException) as exc:
            await repo.create(message)

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestListByCriteria:
    async def test_without_criteria_returns_all_the_users_messages_oldest_first(
        self, repo, session
    ):
        user_id = await _user(session)
        first_chat = await _chat(session, user_id)
        second_chat = await _chat(session, user_id)
        latest = await _message(repo, first_chat, minute=2)
        earliest = await _message(repo, second_chat, minute=0)
        middle = await _message(repo, first_chat, minute=1)

        messages = await repo.list_by_criteria(user_id, None)

        assert _ids(messages) == [earliest, middle, latest]

    async def test_never_returns_another_users_messages(self, repo, session):
        user_id = await _user(session)
        others_chat = await _chat(session, await _user(session))
        await _message(repo, others_chat)

        messages = await repo.list_by_criteria(
            user_id, ChatMessageSearchFilter(chat_session_id=others_chat)
        )

        assert messages == []

    async def test_filters_by_chat_session(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        other_chat = await _chat(session, user_id)
        wanted = await _message(repo, chat_id)
        await _message(repo, other_chat)

        messages = await repo.list_by_criteria(
            user_id, ChatMessageSearchFilter(chat_session_id=chat_id)
        )

        assert _ids(messages) == [wanted]

    async def test_filters_by_role(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        await _message(repo, chat_id, minute=0, role=_USER)
        answer = await _message(repo, chat_id, minute=1, role=_ASSISTANT)

        messages = await repo.list_by_criteria(
            user_id, ChatMessageSearchFilter(role=_ASSISTANT)
        )

        assert _ids(messages) == [answer]

    async def test_combines_chat_session_and_role(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        other_chat = await _chat(session, user_id)
        wanted = await _message(repo, chat_id, role=_ASSISTANT)
        await _message(repo, chat_id, role=_USER)
        await _message(repo, other_chat, role=_ASSISTANT)

        messages = await repo.list_by_criteria(
            user_id, ChatMessageSearchFilter(chat_session_id=chat_id, role=_ASSISTANT)
        )

        assert _ids(messages) == [wanted]

    async def test_breaks_created_at_ties_by_id(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        # Enough rows that an unordered result can't match by chance
        ids = [await _message(repo, chat_id) for _ in range(10)]

        messages = await repo.list_by_criteria(user_id, None)

        assert _ids(messages) == sorted(ids)

    async def test_database_failure_raises_a_server_error(self, repo, session):
        failing = AsyncMock(side_effect=SQLAlchemyError("boom"))

        with (
            patch.object(session, "execute", failing),
            pytest.raises(ApiException) as exc,
        ):
            await repo.list_by_criteria(uuid.uuid4(), None)

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestListByCriteriaPaginated:
    async def test_returns_the_requested_page_newest_first(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        oldest_first = [await _message(repo, chat_id, minute=i) for i in range(5)]

        page = await repo.list_by_criteria_paginated(
            user_id, None, Pagination(page=2, limit=2)
        )

        assert _ids(page.items) == [oldest_first[2], oldest_first[1]]
        assert page.total == 5
        assert page.pages == 3

    async def test_total_counts_only_matching_owned_messages(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        await _message(repo, chat_id, minute=0, role=_ASSISTANT)
        await _message(repo, chat_id, minute=1, role=_ASSISTANT)
        await _message(repo, chat_id, minute=2, role=_USER)
        await _message(
            repo, await _chat(session, await _user(session)), role=_ASSISTANT
        )

        page = await repo.list_by_criteria_paginated(
            user_id, ChatMessageSearchFilter(role=_ASSISTANT), Pagination(limit=10)
        )

        assert page.total == 2
        assert len(page.items) == 2

    async def test_page_past_the_end_is_empty_but_keeps_the_total(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        for minute in range(3):
            await _message(repo, chat_id, minute=minute)

        page = await repo.list_by_criteria_paginated(
            user_id, None, Pagination(page=4, limit=2)
        )

        assert page.items == []
        assert page.total == 3


class TestGetById:
    async def test_returns_the_message(self, repo, session):
        chat_id = await _chat(session, await _user(session))
        message_id = await _message(repo, chat_id, sources=["a.pdf"])

        message = await repo.get_by_id(message_id)

        assert message is not None
        assert message.chat_session_id == chat_id
        assert message.sources == ["a.pdf"]

    async def test_unknown_id_returns_none(self, repo):
        assert await repo.get_by_id(uuid.uuid4()) is None


class TestCount:
    async def test_counts_only_the_chat_sessions_messages(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        other_chat = await _chat(session, user_id)
        for minute in range(3):
            await _message(repo, chat_id, minute=minute)
        await _message(repo, other_chat)

        assert await repo.count(chat_id) == 3

    async def test_chat_session_without_messages_counts_zero(self, repo, session):
        chat_id = await _chat(session, await _user(session))

        assert await repo.count(chat_id) == 0


class TestDeleteAll:
    async def test_deletes_only_the_chat_sessions_messages(self, repo, session):
        user_id = await _user(session)
        chat_id = await _chat(session, user_id)
        other_chat = await _chat(session, user_id)
        for minute in range(3):
            await _message(repo, chat_id, minute=minute)
        kept = await _message(repo, other_chat)

        deleted = await repo.delete_all(chat_id)

        assert deleted == 3
        assert await repo.count(chat_id) == 0
        assert _ids(await repo.list_by_criteria(user_id, None)) == [kept]

    async def test_chat_session_without_messages_deletes_nothing(self, repo, session):
        chat_id = await _chat(session, await _user(session))

        assert await repo.delete_all(chat_id) == 0
