"""Unit tests for header-based API version middleware."""

from collections.abc import Generator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from src.api.middleware.handle_version import APIVersionMiddleware
from src.config.configs import settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    # Pin version settings so assertions stay stable across environments.
    monkeypatch.setattr(settings.server, "API_PREFIX", "/api")
    monkeypatch.setattr(settings.server, "API_V1_PREFIX", "/api/v1")
    monkeypatch.setattr(settings.app, "SUPPORTED_VERSIONS", ["1"])
    monkeypatch.setattr(settings.app, "DEFAULT_VERSION", "1")

    app = FastAPI()
    app.add_middleware(APIVersionMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    @app.get("/api/probe")
    async def probe(request: Request):
        return {"api_version": request.state.api_version}

    @app.get("/api/v1/ping")
    async def ping_legacy():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_defaults_to_configured_version_when_header_missing(client: TestClient):
    response = client.get("/api/ping")

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"
    assert response.headers.get("vary") == "Accept-Version"


def test_accept_version_header_is_honored(client: TestClient):
    response = client.get("/api/ping", headers={"Accept-Version": "v1"})

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"


def test_version_is_saved_on_request_state_for_api_paths(client: TestClient):
    response = client.get("/api/probe", headers={"Accept-Version": "v1"})

    assert response.status_code == 200
    assert response.json() == {"api_version": "1"}


def test_unsupported_header_version_returns_422(client: TestClient):
    response = client.get("/api/ping", headers={"Accept-Version": "2"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported API version '2'. Supported versions: 1."


def test_legacy_v1_path_is_supported_without_header(client: TestClient):
    response = client.get("/api/v1/ping")

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"


def test_legacy_v1_path_rejects_conflicting_header(client: TestClient):
    response = client.get("/api/v1/ping", headers={"Accept-Version": "2"})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Accept-Version header conflicts with URL version. "
        "Use /api routes with Accept-Version or /api/v1 without conflicting header."
    )


def test_non_api_path_bypasses_version_check(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("content-version") is None

