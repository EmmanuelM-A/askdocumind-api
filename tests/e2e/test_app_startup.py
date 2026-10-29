"""
Smoke test that runs the real app lifespan, so a startup crash fails the suite.
"""

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config.configs import settings


@pytest.fixture
def client():
    if not settings.database.DATABASE_URL.get_secret_value():
        pytest.skip("DATABASE_URL is not set")

    # Entering the client runs the lifespan startup, and leaving it runs shutdown
    with TestClient(create_app(), base_url="https://test") as test_client:
        yield test_client


def test_app_starts_and_reports_healthy(client):
    assert client.app.state.session_manager is not None
    assert client.app.state.ingestion_runner is not None
    assert client.app.state.reranker is not None

    for path in ("/health/server", "/health/db"):
        response = client.get(path)

        assert response.status_code == 200, f"{path}: {response.text}"
        assert response.json()["data"] == {"status": "OK"}
