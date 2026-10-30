"""
Unit tests for how CORS_ORIGINS and RERANKER_ENABLED are read from the
environment, including the values that broke a Railway deploy.
"""

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError

from src.config import configs
from src.config.configs import _RAGSettings, _ServerSettings

_BOTH = ["https://askdocumind.com", "https://www.askdocumind.com"]


@pytest.mark.parametrize(
    "raw",
    [
        '["https://askdocumind.com","https://www.askdocumind.com"]',
        "https://askdocumind.com,https://www.askdocumind.com",
        " https://askdocumind.com , https://www.askdocumind.com/ ",
        "https://askdocumind.com,https://www.askdocumind.com,",
    ],
    ids=["json", "comma-separated", "spaces-and-slash", "trailing-comma"],
)
def test_cors_origins_accepts_json_or_comma_separated(monkeypatch, raw):
    monkeypatch.setenv("CORS_ORIGINS", raw)

    assert _ServerSettings().CORS_ORIGINS == _BOTH


def test_cors_origins_accepts_a_single_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://askdocumind.com")

    assert _ServerSettings().CORS_ORIGINS == ["https://askdocumind.com"]


@pytest.mark.parametrize(
    "raw",
    [
        r"[\"https://askdocumind.com\"]",
        "'[\"https://askdocumind.com\"]'",
        "[https://askdocumind.com]",
        "askdocumind.com",
        "*",
        ",",
    ],
    ids=[
        "escaped-quotes",
        "single-quoted",
        "unquoted-json",
        "no-scheme",
        "wildcard",
        "only-comma",
    ],
)
def test_cors_origins_rejects_invalid_values(monkeypatch, raw):
    monkeypatch.setenv("CORS_ORIGINS", raw)

    with pytest.raises((ValidationError, SettingsError)):
        _ServerSettings()


def test_empty_cors_origins_uses_the_default(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")

    assert _ServerSettings().CORS_ORIGINS == ["http://localhost:3000"]


@pytest.mark.parametrize("raw", [None, ""], ids=["unset", "empty"])
@pytest.mark.parametrize("installed", [True, False])
def test_reranker_defaults_to_whether_it_is_installed(monkeypatch, raw, installed):
    if raw is None:
        monkeypatch.delenv("RERANKER_ENABLED", raising=False)
    else:
        monkeypatch.setenv("RERANKER_ENABLED", raw)
    monkeypatch.setattr(configs, "_is_installed", lambda _: installed)

    assert _RAGSettings().RERANKER_ENABLED is installed


def test_reranker_enabled_without_the_package_fails_clearly(monkeypatch):
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setattr(configs, "_is_installed", lambda _: False)

    with pytest.raises(ValidationError, match="WITH_RERANKER=true"):
        _RAGSettings()


@pytest.mark.parametrize("installed", [True, False])
def test_reranker_can_always_be_turned_off(monkeypatch, installed):
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setattr(configs, "_is_installed", lambda _: installed)

    assert _RAGSettings().RERANKER_ENABLED is False
