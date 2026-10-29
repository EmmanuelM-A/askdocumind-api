from http.cookies import Morsel, SimpleCookie
from unittest.mock import MagicMock

import pytest
from fastapi import Response
from pydantic import ValidationError

from src.auth.services.cookie_service import (
    CookieConfig,
    clear_cookie,
    set_cookie,
)

TOKEN = "aaa.bbb_ccc-ddd.eee"


# ============================== Fixtures ==============================


@pytest.fixture
def config() -> CookieConfig:
    return CookieConfig(
        http_only=True,
        secure=True,
        same_site="lax",
        domain="example.com",
    )


@pytest.fixture
def response() -> Response:
    return Response()


@pytest.fixture
def mock_response() -> MagicMock:
    return MagicMock(spec=Response)


@pytest.fixture
def get_cookie():
    """Return the parsed Set-Cookie morsel for a cookie name."""

    def _get(resp: Response, name: str) -> Morsel:
        for header in resp.headers.getlist("set-cookie"):
            jar = SimpleCookie()
            jar.load(header)
            if name in jar:
                return jar[name]
        raise AssertionError(f"Cookie {name!r} was not set")

    return _get


@pytest.fixture
def set_default(response, config):
    """Set a cookie with sensible defaults, overridable per test."""

    def _set(**overrides):
        kwargs = {
            "response": response,
            "cookie_name": "session",
            "cookie_value": TOKEN,
            "max_age_seconds": 3600,
            "path": "/",
            "config": config,
        }
        kwargs.update(overrides)
        return set_cookie(**kwargs)

    return _set


# ============================= Tests ==============================


def test_set_cookie_writes_name_and_value(response, set_default, get_cookie):
    set_default()

    cookie = get_cookie(response, "session")

    assert cookie.value == TOKEN


@pytest.mark.parametrize("http_only", [True, False])
def test_set_cookie_applies_http_only(
    response, config, set_default, get_cookie, http_only
):
    set_default(config=config.model_copy(update={"http_only": http_only}))

    assert bool(get_cookie(response, "session")["httponly"]) is http_only


@pytest.mark.parametrize("secure", [True, False])
def test_set_cookie_applies_secure(response, config, set_default, get_cookie, secure):
    set_default(config=config.model_copy(update={"secure": secure}))

    assert bool(get_cookie(response, "session")["secure"]) is secure


@pytest.mark.parametrize("same_site", ["none", "strict", "lax"])
def test_set_cookie_applies_same_site(
    response, config, set_default, get_cookie, same_site
):
    set_default(config=config.model_copy(update={"same_site": same_site}))

    assert get_cookie(response, "session")["samesite"].lower() == same_site


def test_set_cookie_applies_max_age(response, set_default, get_cookie):
    set_default(max_age_seconds=7200)

    assert get_cookie(response, "session")["max-age"] == "7200"


def test_set_cookie_applies_path(response, set_default, get_cookie):
    set_default(path="/api")

    assert get_cookie(response, "session")["path"] == "/api"


def test_set_cookie_applies_domain(response, set_default, get_cookie):
    set_default()

    assert get_cookie(response, "session")["domain"] == "example.com"


def test_set_cookie_passes_exact_arguments_to_response(mock_response, config):
    set_cookie(
        response=mock_response,
        cookie_name="session",
        cookie_value=TOKEN,
        max_age_seconds=3600,
        path="/",
        config=config,
    )

    mock_response.set_cookie.assert_called_once_with(
        key="session",
        value=TOKEN,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
        path="/",
        domain="example.com",
    )


def test_set_cookie_returns_none(set_default):
    assert set_default() is None


def test_set_cookie_supports_multiple_cookies(response, set_default, get_cookie):
    set_default(cookie_name="first", cookie_value="one")
    set_default(cookie_name="second", cookie_value="two")

    assert get_cookie(response, "first").value == "one"
    assert get_cookie(response, "second").value == "two"


def test_clear_cookie_expires_immediately(response, config, get_cookie):
    clear_cookie(response, "session", "/", config)

    assert get_cookie(response, "session")["max-age"] == "0"


def test_clear_cookie_empties_value(response, config, get_cookie):
    clear_cookie(response, "session", "/", config)

    assert get_cookie(response, "session").value == ""


def test_clear_cookie_applies_config_attributes(response, config, get_cookie):
    clear_cookie(response, "session", "/api", config)

    cookie = get_cookie(response, "session")

    assert cookie["path"] == "/api"
    assert cookie["domain"] == "example.com"
    assert bool(cookie["secure"]) is True
    assert bool(cookie["httponly"]) is True
    assert cookie["samesite"].lower() == "lax"


def test_clear_cookie_passes_exact_arguments_to_response(mock_response, config):
    clear_cookie(mock_response, "session", "/", config)

    mock_response.delete_cookie.assert_called_once_with(
        key="session",
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        domain="example.com",
    )


def test_cookie_config_rejects_invalid_same_site():
    with pytest.raises(ValidationError):
        CookieConfig(
            http_only=True,
            secure=True,
            same_site="sometimes",
            domain="example.com",
        )
