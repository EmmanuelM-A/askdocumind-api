"""
Integration tests for the RequestLoggerMiddleware.
"""

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.middleware.request_logger import RequestLoggerMiddleware

pytestmark = pytest.mark.asyncio

_LOGGER = "src.middleware.request_logger"
_ROOT = "/api"
_PUBLIC_ROUTE = "/health/server"
_SLOW_SECS = 0.05


@pytest_asyncio.fixture
async def client():
    app = FastAPI(redirect_slashes=False, root_path=_ROOT)
    app.add_middleware(
        RequestLoggerMiddleware, exclude_paths=frozenset({_PUBLIC_ROUTE})
    )

    @app.get("/ok")
    async def ok():
        return JSONResponse({"ok": True}, headers={"X-Custom": "kept"})

    @app.post("/status/{code}")
    async def with_status(code: int):
        return JSONResponse({}, status_code=code)

    @app.get("/broken")
    async def broken():
        raise RuntimeError("boom")

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(_SLOW_SECS)
        return {}

    @app.get(_PUBLIC_ROUTE)
    async def public():
        return {}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client


@pytest.fixture
def records(caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    return lambda: [r for r in caplog.records if r.name == _LOGGER]


def _single(records):
    logged = records()
    assert len(logged) == 1
    return logged[0]


# --- Logged requests ---


async def test_successful_request_is_logged_at_info(client, records):
    response = await client.get(f"{_ROOT}/ok", params={"token": "secret"})

    record = _single(records)
    method, path, status_code, duration_ms = record.args
    assert record.levelno == logging.INFO
    assert (method, path, status_code) == ("GET", f"{_ROOT}/ok", 200)
    assert duration_ms >= 0
    assert "secret" not in record.getMessage()
    assert response.json() == {"ok": True}
    assert response.headers["X-Custom"] == "kept"


@pytest.mark.parametrize(
    "code, level",
    [(404, logging.INFO), (503, logging.ERROR)],
    ids=["client-error", "server-error"],
)
async def test_status_code_sets_log_level(client, records, code, level):
    response = await client.post(f"{_ROOT}/status/{code}")

    record = _single(records)
    assert response.status_code == code
    assert record.args[:3] == ("POST", f"{_ROOT}/status/{code}", code)
    assert record.levelno == level


async def test_unhandled_exception_is_logged_as_500(client, records):
    response = await client.get(f"{_ROOT}/broken")

    record = _single(records)
    assert response.status_code == 500
    assert record.args[2] == 500
    assert record.levelno == logging.ERROR


async def test_duration_covers_handler_time(client, records):
    await client.get(f"{_ROOT}/slow")

    assert _single(records).args[3] >= _SLOW_SECS * 1000


async def test_unmatched_route_is_logged(client, records):
    await client.get(f"{_ROOT}/missing")

    assert _single(records).args[1:3] == (f"{_ROOT}/missing", 404)


# --- Excluded requests ---


@pytest.mark.parametrize(
    "path",
    [f"{_ROOT}{_PUBLIC_ROUTE}", _PUBLIC_ROUTE],
    ids=["public-path", "public-path-without-root"],
)
async def test_excluded_path_is_not_logged(client, records, path):
    response = await client.get(path)

    assert response.status_code == 200
    assert records() == []


async def test_non_http_scope_is_passed_through():
    downstream = AsyncMock()
    middleware = RequestLoggerMiddleware(downstream)
    scope = {"type": "lifespan"}
    receive, send = AsyncMock(), AsyncMock()

    await middleware(scope, receive, send)

    downstream.assert_awaited_once_with(scope, receive, send)
