"""
Integration tests for the User Repository.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.auth.models.user import User
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.exceptions.base import ApiException

pytestmark = pytest.mark.asyncio

_INTERNAL_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.fixture
def repo(session):
    return UserRepositoryImpl(session)


async def _add_user(repo, last_seen_at=None, user_id=None):
    user = User(id=user_id or uuid.uuid4())
    if last_seen_at is not None:
        user.last_seen_at = last_seen_at
    await repo.create(user)
    return user


async def _last_seen(session, user_id):
    result = await session.execute(select(User.last_seen_at).where(User.id == user_id))
    return result.scalar_one()


async def _exists(session, user_id):
    result = await session.execute(select(User.id).where(User.id == user_id))
    return result.scalar_one_or_none() is not None


def _fail_execute(session):
    return patch.object(
        session, "execute", AsyncMock(side_effect=SQLAlchemyError("boom"))
    )


class TestCreate:
    async def test_persists_user_with_generated_defaults(self, repo, session):
        user = await repo.create(User())
        await session.refresh(user)

        assert isinstance(user.id, uuid.UUID)
        assert user.created_at is not None
        assert user.last_seen_at is not None
        assert await _exists(session, user.id)

    async def test_returns_same_instance(self, repo):
        user = User()
        assert await repo.create(user) is user

    async def test_keeps_explicit_id(self, repo, session):
        user_id = uuid.uuid4()
        await _add_user(repo, user_id=user_id)
        assert await _exists(session, user_id)

    async def test_explicit_last_seen_is_stored(self, repo, session):
        last_seen = datetime(2024, 1, 1, tzinfo=timezone.utc)
        user = await _add_user(repo, last_seen_at=last_seen)
        assert await _last_seen(session, user.id) == last_seen

    async def test_duplicate_id_raises(self, repo):
        user_id = uuid.uuid4()
        await _add_user(repo, user_id=user_id)

        with pytest.raises(ApiException) as exc:
            await repo.create(User(id=user_id))
        assert exc.value.status_code == _INTERNAL_ERROR

    async def test_flush_failure_raises(self, repo, session):
        with patch.object(
            session, "flush", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            with pytest.raises(ApiException) as exc:
                await repo.create(User())
        assert exc.value.status_code == _INTERNAL_ERROR


class TestGetById:
    async def test_returns_existing_user(self, repo):
        user = await _add_user(repo)
        found = await repo.get_by_id(user.id)
        assert found is not None
        assert found.id == user.id

    async def test_returns_none_for_unknown_id(self, repo):
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_returns_correct_user_among_many(self, repo):
        users = [await _add_user(repo) for _ in range(3)]
        found = await repo.get_by_id(users[1].id)
        assert found.id == users[1].id

    async def test_query_failure_raises(self, repo, session):
        with _fail_execute(session):
            with pytest.raises(ApiException) as exc:
                await repo.get_by_id(uuid.uuid4())
        assert exc.value.status_code == _INTERNAL_ERROR


class TestDelete:
    async def test_deletes_existing_user(self, repo, session):
        user = await _add_user(repo)
        assert await repo.delete(user.id) is True
        assert not await _exists(session, user.id)

    async def test_returns_false_for_unknown_id(self, repo):
        assert await repo.delete(uuid.uuid4()) is False

    async def test_second_delete_returns_false(self, repo):
        user = await _add_user(repo)
        assert await repo.delete(user.id) is True
        assert await repo.delete(user.id) is False

    async def test_leaves_other_users_untouched(self, repo, session):
        target = await _add_user(repo)
        other = await _add_user(repo)
        await repo.delete(target.id)
        assert await _exists(session, other.id)

    async def test_query_failure_raises(self, repo, session):
        with _fail_execute(session):
            with pytest.raises(ApiException) as exc:
                await repo.delete(uuid.uuid4())
        assert exc.value.status_code == _INTERNAL_ERROR


class TestDeleteMany:
    async def test_empty_list_returns_zero_without_querying(self, repo, session):
        with patch.object(session, "execute", AsyncMock()) as execute:
            assert await repo.delete_many([]) == 0
            execute.assert_not_called()

    async def test_deletes_all_given_users(self, repo, session):
        users = [await _add_user(repo) for _ in range(3)]
        ids = [u.id for u in users]

        assert await repo.delete_many(ids) == 3
        for user_id in ids:
            assert not await _exists(session, user_id)

    async def test_leaves_unlisted_users_untouched(self, repo, session):
        doomed = [await _add_user(repo) for _ in range(2)]
        survivor = await _add_user(repo)

        await repo.delete_many([u.id for u in doomed])
        assert await _exists(session, survivor.id)

    async def test_counts_only_existing_users(self, repo):
        user = await _add_user(repo)
        assert await repo.delete_many([user.id, uuid.uuid4(), uuid.uuid4()]) == 1

    async def test_only_unknown_ids_returns_zero(self, repo):
        assert await repo.delete_many([uuid.uuid4(), uuid.uuid4()]) == 0

    async def test_duplicate_ids_count_once(self, repo):
        user = await _add_user(repo)
        assert await repo.delete_many([user.id, user.id]) == 1

    async def test_single_id(self, repo, session):
        user = await _add_user(repo)
        assert await repo.delete_many([user.id]) == 1
        assert not await _exists(session, user.id)

    async def test_query_failure_raises(self, repo, session):
        with _fail_execute(session):
            with pytest.raises(ApiException) as exc:
                await repo.delete_many([uuid.uuid4()])
        assert exc.value.status_code == _INTERNAL_ERROR


class TestUpdateLastSeen:
    @pytest.mark.parametrize(
        "age_mins, freq_mins, should_update",
        [(120, 30, True), (31, 30, True), (29, 30, False), (120, 180, False)],
    )
    async def test_updates_only_when_older_than_frequency(
        self, repo, session, age_mins, freq_mins, should_update
    ):
        old = datetime.now(timezone.utc) - timedelta(minutes=age_mins)
        user = await _add_user(repo, last_seen_at=old)

        await repo.update_last_seen(user.id, freq_mins)

        current = await _last_seen(session, user.id)
        if should_update:
            assert current > old
        else:
            assert current == old

    async def test_fresh_user_is_not_updated(self, repo, session):
        user = await _add_user(repo)
        await session.refresh(user)
        before = user.last_seen_at

        await repo.update_last_seen(user.id, 5)
        assert await _last_seen(session, user.id) == before

    async def test_unknown_user_does_nothing(self, repo):
        assert await repo.update_last_seen(uuid.uuid4(), 5) is None

    async def test_other_users_are_untouched(self, repo, session):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        target = await _add_user(repo, last_seen_at=old)
        other = await _add_user(repo, last_seen_at=old)

        await repo.update_last_seen(target.id, 30)

        assert await _last_seen(session, target.id) > old
        assert await _last_seen(session, other.id) == old

    async def test_created_at_is_not_modified(self, repo, session):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        user = await _add_user(repo, last_seen_at=old)
        await session.refresh(user)
        created_before = user.created_at

        await repo.update_last_seen(user.id, 30)

        result = await session.execute(
            select(User.created_at).where(User.id == user.id)
        )
        assert result.scalar_one() == created_before

    async def test_repeated_calls_within_window_keep_first_update(self, repo, session):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        user = await _add_user(repo, last_seen_at=old)

        await repo.update_last_seen(user.id, 30)
        after_first = await _last_seen(session, user.id)
        await repo.update_last_seen(user.id, 30)

        assert await _last_seen(session, user.id) == after_first

    async def test_query_failure_raises(self, repo, session):
        with _fail_execute(session):
            with pytest.raises(ApiException) as exc:
                await repo.update_last_seen(uuid.uuid4(), 5)
        assert exc.value.status_code == _INTERNAL_ERROR

    async def test_loaded_user_stays_readable_after_update(self, repo):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        user = await _add_user(repo, last_seen_at=old)
        loaded = await repo.get_by_id(user.id)

        await repo.update_last_seen(user.id, 30)

        assert loaded is not None
        assert loaded.last_seen_at is not None
