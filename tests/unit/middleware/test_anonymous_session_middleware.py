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
from src.api.utils.session_manager import AnonymousSessionPayload
from src.config.configs import settings
from src.database.models import User


@pytest.fixture
def middleware_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = Mock()
    repo.get_by_id = AsyncMock()
    repo.update_last_seen = AsyncMock()

    token_manager = Mock()
    token_manager.ttl_seconds = 3600
    token_manager.decode_token = Mock()
    token_manager.create_token = Mock(return_value="refreshed-signed-token")

    monkeypatch.setattr(settings.auth, "COOKIE_NAME", "anon_test_cookie")
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
        return {"state_user_id": str(request.state.anonymous_user_id)}

    @app.get("/api/auth/anonymous")
    async def bootstrap():
        return {"ok": True}

    @app.get("/api/health")
    async def health_api():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_valid_cookie_sets_state_and_refreshes_cookie(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    existing_user_id = uuid4()
    middleware_mocks.token_manager.decode_token.return_value = AnonymousSessionPayload(
        user_id=existing_user_id,
        expires_at=9999999999,
    )
    middleware_mocks.repo.get_by_id.return_value = User(id=existing_user_id)

    client.cookies.set("anon_test_cookie", "valid-token")
    response = client.get("/api/probe")

    assert response.status_code == 200
    assert response.json() == {"state_user_id": str(existing_user_id)}

    middleware_mocks.repo.get_by_id.assert_awaited_once_with(existing_user_id)
    middleware_mocks.repo.update_last_seen.assert_awaited_once_with(
        user_id=existing_user_id
    )
    middleware_mocks.token_manager.create_token.assert_called_with(existing_user_id)
    assert "anon_test_cookie=refreshed-signed-token" in response.headers.get(
        "set-cookie", ""
    )


def test_missing_cookie_on_api_route_returns_error(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/api/probe")

    assert response.status_code >= 400
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
    middleware_mocks.repo.update_last_seen.assert_not_awaited()


def test_missing_user_for_valid_cookie_returns_error(
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

    assert response.status_code >= 400
    middleware_mocks.repo.get_by_id.assert_awaited_once_with(missing_user_id)
    middleware_mocks.repo.update_last_seen.assert_not_awaited()


def test_non_api_path_bypasses_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()


def test_bootstrap_path_bypasses_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/api/auth/anonymous")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()


def test_health_api_path_bypasses_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.get("/api/health")

    assert response.status_code == 200
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()


def test_options_request_bypasses_session_resolution(
    client: TestClient,
    middleware_mocks: SimpleNamespace,
):
    response = client.options("/api/probe")

    assert response.status_code != 401
    middleware_mocks.token_manager.decode_token.assert_not_called()
    middleware_mocks.repo.get_by_id.assert_not_awaited()
