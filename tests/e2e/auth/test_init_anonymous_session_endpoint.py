"""
End-to-end tests for the /auth/anonymous/init endpoint.
"""

import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, patch

import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.dml import Update

from src.auth.dependencies import get_user_repository
from src.auth.models.user import User
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.routes.auth_router import auth_router
from src.auth.services.anonymous_user_service import AnonymousUserService
from src.auth.services.token_service import (
    create_anonymous_token,
    decode_anonymous_token,
)
from src.config.configs import settings
from src.exceptions.handlers import setup_exception_handlers

pytestmark = pytest.mark.asyncio

_ENDPOINT = "/v1/auth/anonymous/init"


@pytest.fixture
def repo(session):
    return UserRepositoryImpl(session)


@pytest_asyncio.fixture
async def auth_client(repo):
    app = FastAPI(redirect_slashes=False)
    app.include_router(auth_router, prefix="/v1")
    setup_exception_handlers(app)
    app.dependency_overrides[get_user_repository] = lambda: repo

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client


def _cookie_header(token):
    return {"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}={token}"}


def _issued_cookie(response):
    jar = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        jar.load(header)
    return jar.get(settings.auth.ANONYMOUS_COOKIE_NAME)


def _encode(payload, secret=None):
    key = secret or settings.auth.ANONYMOUS_TOKEN_SECRET.get_secret_value()
    return jwt.encode(payload, key=key, algorithm="HS256")


def _payload(user_id=None, iat_offset=0, exp_offset=3600):
    now = datetime.now(timezone.utc).timestamp()
    return {
        "user_id": str(user_id or uuid.uuid4()),
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }


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


class TestNewSession:
    async def test_without_cookie_creates_user(self, auth_client, session):
        before = await _count_users(session)

        response = await auth_client.post(_ENDPOINT)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert await _count_users(session) == before + 1
        assert await _exists(session, uuid.UUID(body["data"]["id"]))

    async def test_sets_token_cookie_for_new_user(self, auth_client):
        response = await auth_client.post(_ENDPOINT)

        morsel = _issued_cookie(response)
        assert morsel is not None
        token_user_id = decode_anonymous_token(morsel.value).user_id
        assert str(token_user_id) == response.json()["data"]["id"]

    async def test_cookie_attributes(self, auth_client):
        response = await auth_client.post(_ENDPOINT)

        morsel = _issued_cookie(response)
        assert morsel["httponly"] is True
        assert morsel["secure"] is True
        assert morsel["samesite"].lower() == "strict"
        assert morsel["path"] == "/"
        assert morsel["max-age"] == str(settings.auth.COOKIE_TTL_HOURS * 3600)
        assert morsel["domain"] == (settings.auth.COOKIE_DOMAIN or "")

    async def test_response_is_json(self, auth_client):
        response = await auth_client.post(_ENDPOINT)
        assert response.headers["content-type"].startswith("application/json")

    async def test_empty_cookie_value_creates_user(self, auth_client, session):
        before = await _count_users(session)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(""))

        assert response.status_code == 200
        assert await _count_users(session) == before + 1

    async def test_unrelated_cookies_are_ignored(self, auth_client, session):
        before = await _count_users(session)

        response = await auth_client.post(
            _ENDPOINT, headers={"Cookie": "other=value; theme=dark"}
        )

        assert response.status_code == 200
        assert await _count_users(session) == before + 1

    async def test_requests_without_cookie_create_distinct_users(self, auth_client):
        first = await auth_client.post(_ENDPOINT)
        second = await auth_client.post(_ENDPOINT)

        assert first.json()["data"]["id"] != second.json()["data"]["id"]
        assert _issued_cookie(first).value != _issued_cookie(second).value

    async def test_request_body_and_query_are_ignored(self, auth_client):
        response = await auth_client.post(
            _ENDPOINT + "?foo=bar", json={"unexpected": "data"}
        )
        assert response.status_code == 200


class TestExistingSession:
    async def test_valid_cookie_returns_existing_user(self, auth_client, repo, session):
        user, token = await _existing_user_with_token(repo)
        before = await _count_users(session)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(user.id)
        assert await _count_users(session) == before

    async def test_valid_cookie_reissues_same_token(self, auth_client, repo):
        _, token = await _existing_user_with_token(repo)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert _issued_cookie(response).value == token

    async def test_issued_cookie_resumes_same_user(self, auth_client):
        first = await auth_client.post(_ENDPOINT)
        token = _issued_cookie(first).value

        second = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert second.status_code == 200
        assert second.json()["data"]["id"] == first.json()["data"]["id"]

    async def test_stale_last_seen_is_refreshed(self, auth_client, repo, session):
        stale = datetime.now(timezone.utc) - timedelta(
            minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS + 60
        )
        user, token = await _existing_user_with_token(repo, last_seen_at=stale)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 200
        assert await _last_seen(session, user.id) > stale

    async def test_recent_last_seen_is_not_refreshed(self, auth_client, repo, session):
        user, token = await _existing_user_with_token(repo)
        before = await _last_seen(session, user.id)

        await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert await _last_seen(session, user.id) == before

    async def test_cookie_for_deleted_user_creates_replacement(
        self, auth_client, repo, session
    ):
        user, token = await _existing_user_with_token(repo)
        await repo.delete(user.id)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 200
        new_id = uuid.UUID(response.json()["data"]["id"])
        assert new_id != user.id
        assert await _exists(session, new_id)
        assert _issued_cookie(response).value != token

    async def test_valid_token_for_unknown_user_creates_user(
        self, auth_client, session
    ):
        token = create_anonymous_token(uuid.uuid4())
        before = await _count_users(session)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 200
        assert await _count_users(session) == before + 1


class TestInvalidCookie:
    @pytest.mark.parametrize("token", ["not-a-token", "a.b.c", "x" * 500, "null"])
    async def test_malformed_token_is_unauthorized(self, auth_client, session, token):
        before = await _count_users(session)

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 401
        assert _issued_cookie(response) is None
        assert await _count_users(session) == before

    async def test_tampered_token_is_unauthorized(self, auth_client, repo):
        _, token = await _existing_user_with_token(repo)

        response = await auth_client.post(
            _ENDPOINT, headers=_cookie_header(token + "abc")
        )

        assert response.status_code == 401

    async def test_wrong_secret_is_unauthorized(self, auth_client, repo):
        user, _ = await _existing_user_with_token(repo)
        token = _encode(
            _payload(user.id), secret="a-different-secret-of-sufficient-length"
        )

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 401

    async def test_expired_token_is_unauthorized(self, auth_client, repo):
        user, _ = await _existing_user_with_token(repo)
        token = _encode(_payload(user.id, iat_offset=-7200, exp_offset=-3600))

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 401

    async def test_payload_with_invalid_user_id_is_unauthorized(self, auth_client):
        token = _encode({"user_id": "not-a-uuid", "iat": 1.0, "exp": 9999999999.0})

        response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 401


class TestRouting:
    @pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
    async def test_other_methods_are_not_allowed(self, auth_client, method):
        response = await auth_client.request(method, _ENDPOINT)
        assert response.status_code == 405

    async def test_trailing_slash_is_not_found(self, auth_client):
        response = await auth_client.post(_ENDPOINT + "/")
        assert response.status_code == 404

    async def test_missing_version_prefix_is_not_found(self, auth_client):
        response = await auth_client.post("/auth/anonymous/init")
        assert response.status_code == 404


class TestFailures:
    async def test_user_creation_failure_returns_500(self, auth_client, session):
        with patch.object(
            session, "flush", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            response = await auth_client.post(_ENDPOINT)

        assert response.status_code == 500
        assert _issued_cookie(response) is None

    async def test_lookup_failure_returns_500(self, auth_client, repo, session):
        _, token = await _existing_user_with_token(repo)

        with patch.object(
            session, "execute", AsyncMock(side_effect=SQLAlchemyError("boom"))
        ):
            response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 500
        assert _issued_cookie(response) is None

    async def test_last_seen_update_failure_returns_500(
        self, auth_client, repo, session
    ):
        _, token = await _existing_user_with_token(repo)
        real_execute = session.execute

        async def fail_on_update(statement, *args, **kwargs):
            if isinstance(statement, Update):
                raise SQLAlchemyError("boom")
            return await real_execute(statement, *args, **kwargs)

        with patch.object(session, "execute", fail_on_update):
            response = await auth_client.post(_ENDPOINT, headers=_cookie_header(token))

        assert response.status_code == 500

    async def test_unexpected_service_error_returns_500(self, auth_client):
        with patch.object(
            AnonymousUserService,
            "init_anonymous_user",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = await auth_client.post(_ENDPOINT)

        assert response.status_code == 500
        assert _issued_cookie(response) is None
