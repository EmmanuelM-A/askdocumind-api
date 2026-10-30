"""
Unit tests for the servers listed in the OpenAPI schema.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.app import create_app
from src.config.configs import _ServerSettings, settings


def _served_servers():
    # Not entered as a context manager, so the lifespan (database, model)
    # doesn't run
    response = TestClient(create_app()).get("/openapi.json")
    assert response.status_code == 200
    return response.json()["servers"]


def test_only_the_relative_root_is_listed_by_default(monkeypatch):
    monkeypatch.setattr(settings.server, "API_PUBLIC_URL", None)

    assert _served_servers() == [{"url": "/api"}]


def test_public_url_is_listed_after_the_relative_root(monkeypatch):
    monkeypatch.setattr(
        settings.server, "API_PUBLIC_URL", "https://api.askdocumind.com/api"
    )
    monkeypatch.setattr(settings.server, "ENV", "production")

    assert _served_servers() == [
        {"url": "/api"},
        {"url": "https://api.askdocumind.com/api", "description": "Production"},
    ]


def test_public_url_trailing_slash_is_removed(monkeypatch):
    monkeypatch.setenv("API_PUBLIC_URL", "https://api.askdocumind.com/api/")

    assert _ServerSettings().API_PUBLIC_URL == "https://api.askdocumind.com/api"


def test_public_url_needs_a_scheme(monkeypatch):
    monkeypatch.setenv("API_PUBLIC_URL", "api.askdocumind.com/api")

    with pytest.raises(ValidationError):
        _ServerSettings()
