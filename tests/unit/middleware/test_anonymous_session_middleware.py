"""Unit tests for anonymous session middleware behavior."""

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from src.api.middleware.anonymous_session import AnonymousSessionMiddleware
from src.api.middleware.exception_handler import setup_exception_handlers
from src.api.services.auth.anonymous_identity import (
    get_current_anonymous_user_id,
    require_current_anonymous_user_id,
)
from src.api.utils.session_manager import AnonymousSessionPayload
from src.config.configs import settings
from src.database.models import User


@pytest.fixture
def middleware_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = Mock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()

    token_manager = Mock()
    token_manager.ttl_seconds = 3600
    token_manager.decode_token = Mock()
    token_manager.create_token = Mock(return_value="refreshed-signed-token")

    monkeypatch.setattr(settings.server, "API_PREFIX", "/api")
    monkeypatch.setattr(
        settings.auth,
        "ANON_SESSION_USER_COOKIE_NAME",
        "anon_test_cookie",
    )
    monkeypatch.setattr(
        "src.api.middleware.anonymous_session.get_database_repository",
        Mock(return_value=repo),
    )
    monkeypatch.setattr(
        "src.api.middleware.anonymous_session.get_token_manager",
        Mock(return_value=token_manager),
    )

    return SimpleNamespace(repo=repo, token_manager=token_manager)


@pytest.fixture
def app(middleware_mocks: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)
    app.add_middleware(AnonymousSessionMiddleware)

    @app.get("/api/probe")
    async def probe(request: Request):
        current_user_id = require_current_anonymous_user_id()
        return {
            "state_user_id": str(request.state.anonymous_user_id),
            "context_user_id": str(current_user_id),
        }

    @app.get("/api/auth/anonymous")
    async def bootstrap():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_valid_cookie_refreshes_existing_session(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    existing_user_id = uuid4()
    middleware_mocks.token_manager.decode_token.return_value = AnonymousSessionPayload(
        user_id=existing_user_id,
        expires_at=9999999999,
    )
    middleware_mocks.repo.get_by_id.return_value = User(id=existing_user_id)
    middleware_mocks.repo.update.return_value = User(id=existing_user_id)

    client.cookies.set("anon_test_cookie", "valid-token")
    response = client.get("/api/probe")

    assert response.status_code == 200
    assert response.json() == {
        "state_user_id": str(existing_user_id),
        "context_user_id": str(existing_user_id),
    }

    middleware_mocks.repo.get_by_id.assert_awaited_once_with(existing_user_id)
    middleware_mocks.repo.update.assert_awaited_once()
    update_call = middleware_mocks.repo.update.await_args
    assert update_call.args[0] == existing_user_id
    assert update_call.args[1].last_seen_at is not None

    middleware_mocks.token_manager.create_token.assert_called_once_with(existing_user_id)
    assert "anon_test_cookie=refreshed-signed-token" in response.headers.get(
        "set-cookie", ""
    )

    assert get_current_anonymous_user_id() is None


def test_missing_cookie_on_api_route_returns_422(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/api/probe")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "422: No cookie value provided" in (body["error"].get("details") or "")

    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update.assert_not_awaited()


def test_missing_user_for_valid_cookie_returns_404(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    missing_user_id = uuid4()
    middleware_mocks.token_manager.decode_token.return_value = AnonymousSessionPayload(
        user_id=missing_user_id,
        expires_at=9999999999,
    )
    middleware_mocks.repo.get_by_id.return_value = None

    client.cookies.set("anon_test_cookie", "valid-token")
    response = client.get("/api/probe")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "404: Anonymous session user no longer exists." in (
        body["error"].get("details") or ""
    )
    middleware_mocks.repo.update.assert_not_awaited()


def test_non_api_path_bypasses_middleware_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update.assert_not_awaited()


def test_bootstrap_path_bypasses_middleware_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/api/auth/anonymous")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update.assert_not_awaited()


def test_options_request_bypasses_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.options("/api/probe")

    assert response.status_code != 422
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update.assert_not_awaited()
