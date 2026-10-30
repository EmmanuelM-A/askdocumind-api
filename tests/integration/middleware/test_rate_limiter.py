"""
Integration tests for the rate limiter and its use on the API routes.
"""

import importlib

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from limits import parse
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from src.config.configs import _ServerSettings, settings
from src.health.router import health_check_router
from src.middleware.rate_limiter import (
    DEFAULT_LIMIT,
    chat_session_limit,
    chatbot_limit,
    default_limit,
    limiter,
    rate_limit_exceeded_handler,
)

pytestmark = pytest.mark.asyncio

_ROOT = "/api"
_USER_HEADER = "X-Test-User"
_CHAT_SESSION_MAX = parse(settings.server.RATE_LIMIT_CHAT_SESSION).amount
_HEALTH_SERVER_MAX = parse(settings.server.RATE_LIMIT_HEALTH_SERVER).amount
_DEFAULT_MAX = parse(DEFAULT_LIMIT).amount


class _FakeAnonymousSession:
    """Stands in for AnonymousSessionMiddleware by trusting a test header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            user_id = dict(scope["headers"]).get(_USER_HEADER.lower().encode())
            if user_id:
                scope.setdefault("state", {})["user_id"] = user_id.decode()
        await self.app(scope, receive, send)


# Decorated once at import: SlowAPI adds a limit per decoration of a name
_calls = {"count": 0}


@chat_session_limit
async def _sessions_a(request: Request):
    _calls["count"] += 1
    return {"ok": True}


@chat_session_limit
async def _sessions_b(request: Request):
    return {"ok": True}


@chatbot_limit
async def _chatbot(request: Request):
    return {"ok": True}


@default_limit
async def _default(request: Request):
    return {"ok": True}


@pytest.fixture
def calls():
    _calls["count"] = 0
    return _calls


@pytest.fixture
def app():
    app = FastAPI(redirect_slashes=False, root_path=_ROOT)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIASGIMiddleware)
    app.add_middleware(_FakeAnonymousSession)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(health_check_router)
    app.add_api_route("/sessions-a", _sessions_a)
    app.add_api_route("/sessions-b", _sessions_b)
    app.add_api_route("/chatbot", _chatbot)
    app.add_api_route("/default", _default)
    return app


def _client(app, ip="10.0.0.1"):
    transport = ASGITransport(app=app, client=(ip, 1234))
    return AsyncClient(transport=transport, base_url="https://test")


@pytest_asyncio.fixture
async def client(app):
    async with _client(app) as http_client:
        yield http_client


async def _exhaust(client, path, count, user=None):
    headers = {_USER_HEADER: user} if user else {}
    for _ in range(count):
        assert (await client.get(path, headers=headers)).status_code == 200


def _assert_rate_limited(response, window_secs=60):
    assert response.status_code == 429
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert 1 <= int(response.headers["Retry-After"]) <= window_secs


# --- Limits ---


async def test_request_over_group_limit_is_rejected(client, calls):
    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX, user="u1")

    response = await client.get(f"{_ROOT}/sessions-a", headers={_USER_HEADER: "u1"})

    _assert_rate_limited(response)
    assert calls["count"] == _CHAT_SESSION_MAX


async def test_routes_in_a_group_share_one_budget(client):
    half = _CHAT_SESSION_MAX // 2
    await _exhaust(client, f"{_ROOT}/sessions-a", half, user="u1")
    await _exhaust(client, f"{_ROOT}/sessions-b", _CHAT_SESSION_MAX - half, user="u1")

    response = await client.get(f"{_ROOT}/sessions-b", headers={_USER_HEADER: "u1"})

    _assert_rate_limited(response)


async def test_groups_have_separate_budgets(client):
    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX, user="u1")

    response = await client.get(f"{_ROOT}/chatbot", headers={_USER_HEADER: "u1"})

    assert response.status_code == 200


async def test_default_limit_applies_to_decorated_route(client):
    await _exhaust(client, f"{_ROOT}/default", _DEFAULT_MAX, user="u1")

    response = await client.get(f"{_ROOT}/default", headers={_USER_HEADER: "u1"})

    _assert_rate_limited(response, window_secs=settings.server.RATE_LIMIT_WINDOW_SECS)


async def test_real_health_route_is_limited(client):
    await _exhaust(client, f"{_ROOT}/health/server", _HEALTH_SERVER_MAX)

    _assert_rate_limited(await client.get(f"{_ROOT}/health/server"))


# --- Keys ---


async def test_limits_are_per_anonymous_user(client):
    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX, user="u1")

    response = await client.get(f"{_ROOT}/sessions-a", headers={_USER_HEADER: "u2"})

    assert response.status_code == 200


async def test_anonymous_user_is_not_limited_by_shared_ip(client):
    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX)

    response = await client.get(f"{_ROOT}/sessions-a", headers={_USER_HEADER: "u1"})

    assert response.status_code == 200


async def test_requests_without_session_are_limited_per_ip(app, client):
    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX)

    async with _client(app, ip="10.0.0.2") as other_client:
        response = await other_client.get(f"{_ROOT}/sessions-a")

    assert response.status_code == 200
    _assert_rate_limited(await client.get(f"{_ROOT}/sessions-a"))


# --- Configuration ---


async def test_disabled_limiter_does_not_limit(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", False)

    await _exhaust(client, f"{_ROOT}/sessions-a", _CHAT_SESSION_MAX + 1, user="u1")


async def test_invalid_limit_setting_is_rejected():
    with pytest.raises(ValidationError):
        _ServerSettings(RATE_LIMIT_CHATBOT="lots/minute")


@pytest.mark.parametrize(
    "module, router_name",
    [
        ("src.health.router", "health_check_router"),
        ("src.auth.routes.auth_router", "auth_router"),
        ("src.chat_session.routes.chat_session_router", "chat_session_router"),
        ("src.chatbot.routes.chatbot_router", "chatbot_router"),
        ("src.uploads.routes.upload_router", "upload_router"),
    ],
    ids=["health", "auth", "chat-session", "chatbot", "uploads"],
)
async def test_every_api_route_has_a_rate_limit(module, router_name):
    if router_name == "upload_router":
        pytest.importorskip("python_multipart")
    router = getattr(importlib.import_module(module), router_name)
    expected = {
        "/health/server": settings.server.RATE_LIMIT_HEALTH_SERVER,
        "/health/db": settings.server.RATE_LIMIT_HEALTH_DB,
        "/auth/anonymous/init": DEFAULT_LIMIT,
        "/chat-session": settings.server.RATE_LIMIT_CHAT_SESSION,
        "/chatbot": settings.server.RATE_LIMIT_CHATBOT,
        "/uploads": settings.server.RATE_LIMIT_UPLOADS,
    }
    overrides = {
        "/uploads/{chat_session_id}/{document_id}/status": DEFAULT_LIMIT,
        "/uploads/{chat_session_id}/{file_id}": DEFAULT_LIMIT,
    }

    for route in router.routes:
        assert isinstance(route, APIRoute)
        name = f"{route.endpoint.__module__}.{route.endpoint.__name__}"
        group = next(p for p in expected if route.path.startswith(p))
        limit = overrides.get(route.path, expected[group])

        route_limits = limiter._route_limits.get(name, [])
        assert [lim.limit for lim in route_limits] == [parse(limit)], route.path
