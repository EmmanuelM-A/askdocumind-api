"""Unit tests for header-based API version middleware."""

from collections.abc import Generator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from src.api.middleware.handle_version import APIVersionMiddleware
from src.config.configs import settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings.app, "DEFAULT_VERSION", "1")

    app = FastAPI()
    app.add_middleware(APIVersionMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    @app.get("/api/probe")
    async def probe(request: Request):
        return {"api_version": request.state.api_version}

    @app.get("/health")
    async def health():
        return {"ok": True}

    with TestClient(app) as test_client:
        yield test_client


def test_no_header_uses_default_version(client: TestClient):
    response = client.get("/api/ping")

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"


def test_accept_version_header_is_normalised(client: TestClient):
    response = client.get("/api/ping", headers={"Accept-Version": "v1"})

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"


def test_accept_version_without_v_prefix(client: TestClient):
    response = client.get("/api/ping", headers={"Accept-Version": "1"})

    assert response.status_code == 200
    assert response.headers.get("content-version") == "1"


def test_version_is_stored_on_request_state(client: TestClient):
    response = client.get("/api/probe", headers={"Accept-Version": "v1"})

    assert response.status_code == 200
    assert response.json() == {"api_version": "1"}


def test_vary_header_is_set_for_api_paths(client: TestClient):
    response = client.get("/api/ping")

    vary = response.headers.get("vary", "")
    assert "Accept-Version" in vary


def test_vary_header_appends_to_existing_vary(client: TestClient):
    """Middleware should append to an existing Vary header, not replace it."""
    response = client.get("/api/ping")

    vary = response.headers.get("vary", "")
    assert "Accept-Version" in vary


def test_non_api_path_bypasses_middleware(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("content-version") is None
    assert "Accept-Version" not in response.headers.get("vary", "")


def test_options_request_bypasses_middleware(client: TestClient):
    response = client.options("/api/ping")

    assert response.headers.get("content-version") is None
