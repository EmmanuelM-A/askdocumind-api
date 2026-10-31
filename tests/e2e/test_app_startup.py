"""
Smoke test that runs the real app lifespan, so a startup crash fails the suite.
"""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.app import create_app
from src.config.configs import settings
from src.rag.services.rerank.cross_encoder_reranker import CrossEncoderReranker
from src.rag.services.rerank.passthrough_reranker import PassthroughReranker


@pytest.fixture
def client():
    if not settings.database.DATABASE_URL.get_secret_value():
        pytest.skip("DATABASE_URL is not set")

    # Entering the client runs the lifespan startup, and leaving it runs shutdown
    with TestClient(create_app(), base_url="https://test") as test_client:
        yield test_client


def _assert_healthy(client):
    for path in ("/health/server", "/health/db"):
        response = client.get(path)

        assert response.status_code == 200, f"{path}: {response.text}"
        assert response.json()["data"] == {"status": "OK"}


def test_app_starts_and_reports_healthy(client):
    assert client.app.state.session_manager is not None
    assert client.app.state.ingestion_runner is not None
    assert isinstance(client.app.state.reranker, CrossEncoderReranker)

    _assert_healthy(client)


def test_app_starts_with_reranker_disabled_and_null_pool(monkeypatch):
    if not settings.database.DATABASE_URL.get_secret_value():
        pytest.skip("DATABASE_URL is not set")
    monkeypatch.setattr(settings.rag, "RERANKER_ENABLED", False)
    monkeypatch.setattr(settings.database, "DB_USE_NULL_POOL", True)

    with TestClient(create_app(), base_url="https://test") as client:
        assert isinstance(client.app.state.reranker, PassthroughReranker)
        _assert_healthy(client)


def test_app_refuses_to_start_when_the_bucket_is_missing(monkeypatch):
    if not settings.database.DATABASE_URL.get_secret_value():
        pytest.skip("DATABASE_URL is not set")
    monkeypatch.setattr(
        settings.uploads, "S3_BUCKET_NAME", f"missing-{uuid.uuid4().hex}"
    )
    app = create_app()

    with pytest.raises(HTTPException) as exc_info:
        with TestClient(app, base_url="https://test"):
            pass

    assert exc_info.value.status_code == 500
    assert not hasattr(app.state, "session_manager")
