"""Unit tests for anonymous session middleware behavior."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from collections.abc import Generator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from src.api.middleware.anonymous_session import AnonymousSessionMiddleware
from src.api.utils.session_identity import (
    AnonymousSessionPayload,
    get_current_user_id,
    require_current_anonymous_user_id,
)
from src.config.configs import settings
from src.database.models import User


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 2, 12, 0, 0)


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AnonymousSessionMiddleware)

    @app.get("/api/v1/probe")
    async def probe(request: Request):
        current_user_id = require_current_anonymous_user_id()
        return {
            "state_user_id": str(request.state.anonymous_user_id),
            "context_user_id": str(current_user_id),
        }

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_settings_patch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings.auth, "ANON_SESSION_COOKIE_NAME", "anon_test_cookie")
    monkeypatch.setattr(settings.auth, "ANON_SESSION_REFRESH_EVERY_REQUEST", True)
    monkeypatch.setattr(settings.auth, "ANON_SESSION_COOKIE_HTTP_ONLY", True)
    monkeypatch.setattr(settings.auth, "ANON_SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(settings.auth, "ANON_SESSION_COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(settings.auth, "ANON_SESSION_COOKIE_DOMAIN", None)


@pytest.fixture
def middleware_mocks(monkeypatch: pytest.MonkeyPatch, fixed_now: datetime):
    repo = Mock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()

    token_manager = Mock()
    token_manager.ttl_seconds = 3600
    token_manager.decode_token = Mock()
    token_manager.create_token = Mock(return_value="new-signed-token")

    user_repo_ctor = Mock(return_value=repo)

    monkeypatch.setattr(
        "src.api.middleware.anonymous_session.UserRepository", user_repo_ctor
    )
    monkeypatch.setattr(
        "src.api.middleware.anonymous_session.get_anonymous_session_token_manager",
        Mock(return_value=token_manager),
    )
    monkeypatch.setattr(
        "src.api.middleware.anonymous_session.get_database_connection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr("src.api.middleware.anonymous_session.utc_now_naive", lambda: fixed_now)

    return SimpleNamespace(repo=repo, token_manager=token_manager, user_repo_ctor=user_repo_ctor)


def test_creates_anonymous_session_when_cookie_is_missing(
    client: TestClient,
    auth_settings_patch,
    middleware_mocks,
):
    new_user_id = uuid4()
    middleware_mocks.repo.create.return_value = new_user_id

    response = client.get("/api/v1/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["state_user_id"] == str(new_user_id)
    assert body["context_user_id"] == str(new_user_id)

    middleware_mocks.repo.create.assert_awaited_once()
    middleware_mocks.repo.update.assert_not_awaited()
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.token_manager.create_token.assert_called_once_with(new_user_id)

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "anon_test_cookie=new-signed-token" in set_cookie_header


def test_refreshes_existing_session_when_cookie_is_valid(
    client: TestClient,
    auth_settings_patch,
    middleware_mocks,
    fixed_now: datetime,
):
    existing_user_id = uuid4()
    middleware_mocks.token_manager.decode_token.return_value = AnonymousSessionPayload(
        user_id=existing_user_id,
        expires_at=9999999999,
    )
    middleware_mocks.repo.get_by_id.return_value = User(id=existing_user_id)
    middleware_mocks.repo.update.return_value = User(id=existing_user_id)

    client.cookies.set("anon_test_cookie", "valid-token")
    response = client.get("/api/v1/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["state_user_id"] == str(existing_user_id)
    assert body["context_user_id"] == str(existing_user_id)

    middleware_mocks.repo.create.assert_not_awaited()
    middleware_mocks.repo.get_by_id.assert_awaited_once_with(existing_user_id)
    middleware_mocks.repo.update.assert_awaited_once()

    update_call = middleware_mocks.repo.update.await_args
    assert update_call.args[0] == existing_user_id
    update_data = update_call.args[1]
    assert update_data.last_seen_at == fixed_now.isoformat()
    assert update_data.expires_at == "2026-04-02T13:00:00"

    middleware_mocks.token_manager.create_token.assert_called_once_with(existing_user_id)


def test_invalid_cookie_falls_back_to_new_session_and_resets_context(
    client: TestClient,
    auth_settings_patch,
    middleware_mocks,
):
    middleware_mocks.token_manager.decode_token.side_effect = ValueError("bad token")
    new_user_id = uuid4()
    middleware_mocks.repo.create.return_value = new_user_id

    client.cookies.set("anon_test_cookie", "bad-token")
    response = client.get("/api/v1/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["state_user_id"] == str(new_user_id)
    assert body["context_user_id"] == str(new_user_id)

    middleware_mocks.repo.create.assert_awaited_once()
    middleware_mocks.repo.update.assert_not_awaited()
    middleware_mocks.token_manager.create_token.assert_called_once_with(new_user_id)

    # ContextVar should be cleared once request processing completes.
    assert get_current_user_id() is None


def test_non_api_path_bypasses_middleware_session_resolution(
    client: TestClient,
    auth_settings_patch,
    middleware_mocks,
):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    middleware_mocks.repo.create.assert_not_awaited()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update.assert_not_awaited()
