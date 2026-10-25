"""
Integration tests for the ExpiredUserCleaner against a real database.

The cleaner deletes every expired user it can see, so the tests move the
cutoff back to 2000 and date their own users around it. Real users, last seen
far later, are never inside the cutoff.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

import src.database.models  # noqa: F401  registers every model for the mappers
from src.auth.models.user import User
from src.chat_session.domain.chat import ChatMessageRole
from src.chat_session.models.chat_message import ChatMessage
from src.chat_session.models.chat_session import ChatSession
from src.cleanup.expired_user_cleaner import (
    ExpiredUserCleaner,
    ExpiredUserCleanerConfig,
)
from src.config.configs import settings
from src.uploads.models.document import Document
from src.uploads.storage.object_storage import ObjectStorage

pytestmark = pytest.mark.asyncio

_CUTOFF = datetime(2000, 1, 1, tzinfo=timezone.utc)
_EXPIRED = _CUTOFF - timedelta(days=365)
_ACTIVE = _CUTOFF + timedelta(days=365)


def _config(**overrides) -> ExpiredUserCleanerConfig:
    inactive_for = timedelta(
        hours=settings.auth.ANONYMOUS_TOKEN_TTL_HOURS,
        minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS,
    )
    grace = datetime.now(timezone.utc) - _CUTOFF - inactive_for
    return ExpiredUserCleanerConfig(
        grace_seconds=int(grace.total_seconds()), **overrides
    )


@pytest.fixture
def storage():
    return MagicMock(spec=ObjectStorage)


@pytest.fixture
def cleaner(manager, storage):
    return ExpiredUserCleaner(manager, storage, _config())


@pytest_asyncio.fixture
async def make_user(manager):
    """Create a committed user with one chat session, message and document."""
    created = []

    async def _make(last_seen_at):
        async with manager.get_session() as session:
            user = User(last_seen_at=last_seen_at)
            session.add(user)
            await session.flush()
            chat_session = ChatSession(user_id=user.id, title="test")
            session.add(chat_session)
            await session.flush()
            session.add_all(
                [
                    ChatMessage(
                        chat_session_id=chat_session.id,
                        role=ChatMessageRole.USER,
                        content="hi",
                        sources=[],
                    ),
                    Document(
                        chat_session_id=chat_session.id,
                        original_filename="a.txt",
                        object_key=f"{chat_session.id}/{user.id}",
                        content_type="text/plain",
                        size_bytes=1,
                        checksum="x",
                    ),
                ]
            )
        created.append(user.id)
        return user.id, chat_session.id

    yield _make

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id.in_(created)))


async def _count(manager, model, column, value):
    async with manager.get_session() as session:
        statement = select(func.count()).select_from(model).where(column == value)
        return (await session.execute(statement)).scalar_one()


async def _user_data_counts(manager, user_id, chat_session_id):
    return (
        await _count(manager, User, User.id, user_id),
        await _count(manager, ChatSession, ChatSession.id, chat_session_id),
        await _count(
            manager, ChatMessage, ChatMessage.chat_session_id, chat_session_id
        ),
        await _count(manager, Document, Document.chat_session_id, chat_session_id),
    )


# --- Deleting ---


async def test_expired_user_and_their_data_are_deleted(cleaner, manager, make_user):
    user_id, chat_session_id = await make_user(_EXPIRED)

    deleted = await cleaner.clean_once()

    assert deleted == 1
    assert await _user_data_counts(manager, user_id, chat_session_id) == (0, 0, 0, 0)


async def test_expired_users_files_are_deleted(cleaner, storage, make_user):
    _, chat_session_id = await make_user(_EXPIRED)

    await cleaner.clean_once()

    storage.delete_prefix.assert_called_once_with(f"{chat_session_id}/")


async def test_active_user_is_kept(cleaner, manager, storage, make_user):
    user_id, chat_session_id = await make_user(_ACTIVE)

    deleted = await cleaner.clean_once()

    assert deleted == 0
    assert await _user_data_counts(manager, user_id, chat_session_id) == (1, 1, 1, 1)
    storage.delete_prefix.assert_not_called()


async def test_backlog_larger_than_a_batch_is_cleared(manager, storage, make_user):
    cleaner = ExpiredUserCleaner(manager, storage, _config(batch_limit=2))
    users = [await make_user(_EXPIRED) for _ in range(5)]

    deleted = await cleaner.clean_once()

    assert deleted == 5
    for user_id, _ in users:
        assert await _count(manager, User, User.id, user_id) == 0


async def test_failed_file_delete_does_not_stop_cleanup(
    cleaner, manager, storage, make_user
):
    users = [await make_user(_EXPIRED) for _ in range(2)]
    storage.delete_prefix.side_effect = [RuntimeError("storage down"), 1]

    deleted = await cleaner.clean_once()

    assert deleted == 2
    assert storage.delete_prefix.call_count == 2
    for user_id, _ in users:
        assert await _count(manager, User, User.id, user_id) == 0


# --- Cutoff ---


async def test_cutoff_waits_for_token_expiry_and_grace(manager, storage):
    cleaner = ExpiredUserCleaner(manager, storage, ExpiredUserCleanerConfig())
    expected = (
        datetime.now(timezone.utc)
        - timedelta(hours=settings.auth.ANONYMOUS_TOKEN_TTL_HOURS)
        - timedelta(minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS)
        - timedelta(seconds=ExpiredUserCleanerConfig().grace_seconds)
    )

    assert abs(cleaner.cutoff() - expected) < timedelta(seconds=5)


# --- Lifecycle ---


async def test_loop_keeps_running_after_a_failed_pass(manager, storage):
    cleaner = ExpiredUserCleaner(manager, storage, _config(interval_seconds=0))
    calls = AsyncMock(side_effect=[RuntimeError("db down"), 0, 0, 0])

    with patch.object(cleaner, "clean_once", calls):
        cleaner.start()
        async with asyncio.timeout(2):
            while calls.await_count < 2:
                await asyncio.sleep(0)
        await cleaner.stop()

    assert calls.await_count >= 2


async def test_stop_without_start_is_a_no_op(cleaner):
    await cleaner.stop()
