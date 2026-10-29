"""
Integration tests for the AnonymousSessionMiddleware.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models.user import User
from src.auth.services.token_service import create_anonymous_token
from src.config.configs import settings
from src.middleware.anonymous_sessions import AnonymousSessionMiddleware

pytestmark = pytest.mark.asyncio

_ROOT = "/api"
_PROTECTED = f"{_ROOT}/v1/protected"
_INIT = f"{_ROOT}/v1/auth/anonymous/init"
_PUBLIC_ROUTE = "/health/server"
_PUBLIC = f"{_ROOT}{_PUBLIC_ROUTE}"
_ALL_METHODS = ["GET", "POST", "OPTIONS"]


@pytest_asyncio.fixture
async def client(manager):
    app = FastAPI(redirect_slashes=False, root_path=_ROOT)
    app.add_middleware(
        AnonymousSessionMiddleware, exclude_paths=frozenset({_PUBLIC_ROUTE})
    )
    app.state.session_manager = manager

    @app.api_route("/{path:path}", methods=_ALL_METHODS)
    async def catch_all(request: Request):
        user_id = getattr(request.state, "user_id", None)
        return {"user_id": str(user_id) if user_id else None}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def user(manager):
    async with manager.get_session() as session:
        new_user = User()
        session.add(new_user)
        await session.flush()

    yield new_user

    async with manager.get_session() as session:
        await session.execute(delete(User).where(User.id == new_user.id))


def _cookie_header(token):
    return {"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}={token}"}


def _encode(user_id, exp_offset=3600, secret=None):
    now = datetime.now(UTC).timestamp()
    payload = {"user_id": str(user_id), "iat": now, "exp": now + exp_offset}
    key = secret or settings.auth.ANONYMOUS_TOKEN_SECRET.get_secret_value()
    return jwt.encode(payload, key=key, algorithm="HS256")


async def _set_last_seen(manager, user_id, last_seen_at):
    async with manager.get_session() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(last_seen_at=last_seen_at)
        )


async def _get_last_seen(manager, user_id):
    async with manager.get_session() as session:
        result = await session.execute(
            select(User.last_seen_at).where(User.id == user_id)
        )
        return result.scalar_one()


def _assert_error(response, status_code, error_code):
    assert response.status_code == status_code
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == error_code


# --- Valid sessions ---


async def test_valid_cookie_passes_user_id_to_downstream(client, user):
    response = await client.get(
        _PROTECTED, headers=_cookie_header(create_anonymous_token(user.id))
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}


async def test_stale_last_seen_is_refreshed(client, manager, user):
    stale = datetime.now(UTC) - timedelta(
        minutes=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS + 1
    )
    await _set_last_seen(manager, user.id, stale)

    response = await client.get(
        _PROTECTED, headers=_cookie_header(create_anonymous_token(user.id))
    )

    assert response.status_code == 200
    assert await _get_last_seen(manager, user.id) > stale


async def test_recent_last_seen_is_not_refreshed(client, manager, user):
    recent = datetime.now(UTC) - timedelta(seconds=30)
    await _set_last_seen(manager, user.id, recent)

    response = await client.get(
        _PROTECTED, headers=_cookie_header(create_anonymous_token(user.id))
    )

    assert response.status_code == 200
    assert await _get_last_seen(manager, user.id) == recent


# --- Rejected sessions ---


async def test_missing_cookie_is_rejected(client):
    response = await client.get(_PROTECTED)

    _assert_error(response, 401, "ANONYMOUS_COOKIE_REQUIRED")


async def test_empty_cookie_is_rejected(client):
    response = await client.get(_PROTECTED, headers=_cookie_header(""))

    _assert_error(response, 401, "ANONYMOUS_COOKIE_REQUIRED")


@pytest.mark.parametrize(
    "token_factory, error_code",
    [
        (lambda: "not-a-jwt", "TOKEN_INVALID"),
        (lambda: _encode(uuid.uuid4(), secret="wrong-secret" * 4), "TOKEN_INVALID"),
        (lambda: _encode(uuid.uuid4(), exp_offset=-60), "TOKEN_EXPIRED"),
    ],
    ids=["malformed", "wrong-secret", "expired"],
)
async def test_invalid_token_is_rejected(client, token_factory, error_code):
    response = await client.get(_PROTECTED, headers=_cookie_header(token_factory()))

    _assert_error(response, 401, error_code)


async def test_unknown_user_is_rejected(client):
    response = await client.get(
        _PROTECTED, headers=_cookie_header(create_anonymous_token(uuid.uuid4()))
    )

    _assert_error(response, 401, "ANONYMOUS_USER_NOT_FOUND")


async def test_database_error_is_returned_as_api_error(client, user):
    token = create_anonymous_token(user.id)
    db_down = OperationalError("SELECT", {}, Exception("connection refused"))

    with patch.object(AsyncSession, "execute", AsyncMock(side_effect=db_down)):
        response = await client.get(_PROTECTED, headers=_cookie_header(token))

    _assert_error(response, 503, "DATABASE_UNAVAILABLE")


# --- Excluded requests ---


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", _PUBLIC),
        ("GET", f"{_PUBLIC}/"),
        ("GET", _PUBLIC_ROUTE),
        ("OPTIONS", _PROTECTED),
        ("POST", _INIT),
    ],
    ids=[
        "public-path",
        "public-path-trailing-slash",
        "public-path-without-root",
        "preflight",
        "session-init",
    ],
)
async def test_excluded_requests_bypass_authentication(client, method, path):
    response = await client.request(method, path)

    assert response.status_code == 200
    assert response.json() == {"user_id": None}


@pytest.mark.parametrize(
    "method, path",
    [("GET", _INIT), ("POST", f"{_ROOT}/v1/other/auth/anonymous/init")],
    ids=["init-non-post", "init-suffix-on-other-path"],
)
async def test_only_exact_init_post_bypasses_authentication(client, method, path):
    response = await client.request(method, path)

    _assert_error(response, 401, "ANONYMOUS_COOKIE_REQUIRED")


async def test_non_http_scope_is_passed_through():
    downstream = AsyncMock()
    middleware = AnonymousSessionMiddleware(downstream)
    scope = {"type": "lifespan"}
    receive, send = AsyncMock(), AsyncMock()

    await middleware(scope, receive, send)

    downstream.assert_awaited_once_with(scope, receive, send)
