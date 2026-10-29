"""
Integration tests for the AnonymousUserService class.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.dml import Update

from src.auth.models.user import User
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.services.anonymous_user_service import AnonymousUserService
from src.auth.services.token_service import (
    create_anonymous_token,
    decode_anonymous_token,
)
from src.config.configs import settings
from src.exceptions.base import ApiException

pytestmark = pytest.mark.asyncio

INTERNAL_ERROR = 500
UNAUTHORIZED = 401


@pytest.fixture
def repo(session):
    return UserRepositoryImpl(session)


@pytest.fixture
def service(repo):
    return AnonymousUserService(repo)


async def _count_users(session):
    result = await session.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def _exists(session, user_id):
    result = await session.execute(select(User.id).where(User.id == user_id))
    return result.scalar_one_or_none() is not None


async def _last_seen(session, user_id):
    result = await session.execute(select(User.last_seen_at).where(User.id == user_id))
    return result.scalar_one()


async def _existing_user_with_token(repo, last_seen_at=None):
    user = User()
    if last_seen_at is not None:
        user.last_seen_at = last_seen_at
    await repo.create(user)
    return user, create_anonymous_token(user.id)


def _assert_refreshed(new_token, old_token, user_id):
    new, old = decode_anonymous_token(new_token), decode_anonymous_token(old_token)
    assert new.user_id == user_id
    assert new.exp >= old.exp


class TestNewUserCreation:
    @pytest.mark.parametrize("token", [None, "", " ", "\n\t "])
    async def test_missing_or_blank_token_creates_user(self, service, session, token):
        before = await _count_users(session)

        viewable, new_token = await service.init_anonymous_user(token)

        assert await _count_users(session) == before + 1
        assert await _exists(session, viewable.id)
        assert new_token

    async def test_called_without_argument_creates_user(self, service, session):
        viewable, _ = await service.init_anonymous_user()
        assert await _exists(session, viewable.id)

    async def test_new_token_identifies_new_user(self, service):
        viewable, token = await service.init_anonymous_user()
        assert decode_anonymous_token(token).user_id == viewable.id

    async def test_viewable_timestamps_are_iso_strings(self, service):
        viewable, _ = await service.init_anonymous_user()
        datetime.fromisoformat(viewable.created_at)
        datetime.fromisoformat(viewable.last_seen_at)

    async def test_each_call_creates_distinct_user_and_token(self, service):
        first, first_token = await service.init_anonymous_user()
        second, second_token = await service.init_anonymous_user()

        assert first.id != second.id
        assert first_token != second_token

    async def test_returned_token_resumes_same_user(self, service, session):
        created, token = await service.init_anonymous_user()
        before = await _count_users(session)

        resumed, resumed_token = await service.init_anonymous_user(token)

        assert resumed.id == created.id
        _assert_refreshed(resumed_token, token, created.id)
        assert await _count_users(session) == before


class TestExistingUser:
    async def test_valid_token_returns_existing_user(self, service, repo, session):
        user, token = await _existing_user_with_token(repo)
        before = await _count_users(session)

        viewable, returned_token = await service.init_anonymous_user(token)

        assert viewable.id == user.id
        _assert_refreshed(returned_token, token, user.id)
        assert await _count_users(session) == before

    async def test_token_with_surrounding_whitespace_is_stripped(self, service, repo):
        user, token = await _existing_user_with_token(repo)

        viewable, returned_token = await service.init_anonymous_user(f"  {token}\n")

        assert viewable.id == user.id
        _assert_refreshed(returned_token, token, user.id)

    async def test_stale_last_seen_is_refreshed(self, service, repo, session):
        stale = datetime.now(UTC) - timedelta(
            minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS + 60
        )
        user, token = await _existing_user_with_token(repo, last_seen_at=stale)

        await service.init_anonymous_user(token)

        assert await _last_seen(session, user.id) > stale

    async def test_recent_last_seen_is_not_refreshed(self, service, repo, session):
        user, token = await _existing_user_with_token(repo)
        before = await _last_seen(session, user.id)

        await service.init_anonymous_user(token)

        assert await _last_seen(session, user.id) == before

    async def test_other_users_are_untouched(self, service, repo, session):
        stale = datetime.now(UTC) - timedelta(
            minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS + 60
        )
        _, token = await _existing_user_with_token(repo, last_seen_at=stale)
        other, _ = await _existing_user_with_token(repo, last_seen_at=stale)

        await service.init_anonymous_user(token)

        assert await _last_seen(session, other.id) == stale


class TestTokenForDeletedUser:
    async def test_creates_replacement_user(self, service, repo, session):
        user, token = await _existing_user_with_token(repo)
        await repo.delete(user.id)

        viewable, new_token = await service.init_anonymous_user(token)

        assert viewable.id != user.id
        assert await _exists(session, viewable.id)
        assert not await _exists(session, user.id)
        assert new_token != token

    async def test_replacement_token_identifies_replacement_user(self, service, repo):
        user, token = await _existing_user_with_token(repo)
        await repo.delete(user.id)

        viewable, new_token = await service.init_anonymous_user(token)

        assert decode_anonymous_token(new_token).user_id == viewable.id

    async def test_unknown_user_id_in_valid_token_creates_user(self, service, session):
        token = create_anonymous_token(uuid.uuid4())
        before = await _count_users(session)

        _, new_token = await service.init_anonymous_user(token)

        assert await _count_users(session) == before + 1
        assert new_token != token


def _encode(payload, secret=None):
    key = secret or settings.auth.ANONYMOUS_TOKEN_SECRET.get_secret_value()
    return jwt.encode(payload, key=key, algorithm="HS256")


def _payload(user_id=None, iat_offset=0, exp_offset=3600):
    now = datetime.now(UTC).timestamp()
    return {
        "user_id": str(user_id or uuid.uuid4()),
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }


class TestInvalidToken:
    @pytest.mark.parametrize(
        "token", ["not-a-token", "a.b.c", "x" * 500, "Bearer abc", "null"]
    )
    async def test_malformed_token_is_unauthorized(self, service, session, token):
        before = await _count_users(session)

        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(token)

        assert exc.value.status_code == UNAUTHORIZED
        assert await _count_users(session) == before

    async def test_tampered_token_is_unauthorized(self, service, repo):
        _, token = await _existing_user_with_token(repo)

        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(token + "abc")

        assert exc.value.status_code == UNAUTHORIZED

    async def test_token_signed_with_wrong_secret_is_unauthorized(self, service, repo):
        user, _ = await _existing_user_with_token(repo)
        token = _encode(
            _payload(user.id), secret="a-different-secret-of-sufficient-length"
        )

        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(token)

        assert exc.value.status_code == UNAUTHORIZED

    async def test_expired_token_is_unauthorized(self, service, repo, session):
        user, _ = await _existing_user_with_token(repo)
        token = _encode(_payload(user.id, iat_offset=-7200, exp_offset=-3600))
        before = await _count_users(session)

        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(token)

        assert exc.value.status_code == UNAUTHORIZED
        assert await _count_users(session) == before

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"user_id": "not-a-uuid", "iat": 1.0, "exp": 9999999999.0},
            {"iat": 1.0, "exp": 9999999999.0},
            {"user_id": str(uuid.uuid4()), "exp": 9999999999.0},
        ],
    )
    async def test_invalid_payload_is_unauthorized(self, service, payload):
        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(_encode(payload))

        assert exc.value.status_code == UNAUTHORIZED

    async def test_unsigned_token_is_unauthorized(self, service):
        token = jwt.encode(_payload(), key=None, algorithm="none")

        with pytest.raises(ApiException) as exc:
            await service.init_anonymous_user(token)

        assert exc.value.status_code == UNAUTHORIZED

    async def test_invalid_token_does_not_query_database(self, service, session):
        with patch.object(session, "execute", AsyncMock()) as execute:
            with pytest.raises(ApiException):
                await service.init_anonymous_user("not-a-token")
            execute.assert_not_called()


class TestDatabaseFailures:
    async def test_create_failure_raises(self, service, session):
        with patch.object(
            session, "flush", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            with pytest.raises(ApiException) as exc:
                await service.init_anonymous_user()
        assert exc.value.status_code == INTERNAL_ERROR

    async def test_lookup_failure_raises(self, service, repo, session):
        _, token = await _existing_user_with_token(repo)
        with patch.object(
            session, "execute", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            with pytest.raises(ApiException) as exc:
                await service.init_anonymous_user(token)
        assert exc.value.status_code == INTERNAL_ERROR

    async def test_last_seen_update_failure_raises(self, service, repo, session):
        _, token = await _existing_user_with_token(repo)
        real_execute = session.execute

        async def fail_on_update(statement, *args, **kwargs):
            if isinstance(statement, Update):
                raise SQLAlchemyError("boom")
            return await real_execute(statement, *args, **kwargs)

        with patch.object(session, "execute", fail_on_update):
            with pytest.raises(ApiException) as exc:
                await service.init_anonymous_user(token)
        assert exc.value.status_code == INTERNAL_ERROR

    async def test_failed_lookup_creates_no_user(self, service, repo, session):
        _, token = await _existing_user_with_token(repo)
        before = await _count_users(session)

        with patch.object(
            session, "execute", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            with pytest.raises(ApiException):
                await service.init_anonymous_user(token)

        assert await _count_users(session) == before
