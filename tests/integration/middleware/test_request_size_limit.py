"""
Integration tests for the RequestSizeLimitMiddleware.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI, File, Request, UploadFile
from httpx import ASGITransport, AsyncClient

from src.exceptions.handlers import setup_exception_handlers
from src.middleware import request_size_limit
from src.middleware.request_size_limit import RequestSizeLimitMiddleware

pytestmark = pytest.mark.asyncio

_MAX_BYTES = 100


@pytest.fixture
def calls():
    return {"count": 0}


@pytest_asyncio.fixture
async def client(monkeypatch, calls):
    monkeypatch.setattr(request_size_limit, "_MAX_REQUEST_BODY_SIZE", _MAX_BYTES)

    app = FastAPI(redirect_slashes=False)
    app.add_middleware(RequestSizeLimitMiddleware)
    setup_exception_handlers(app)

    @app.post("/raw")
    async def raw(request: Request):
        calls["count"] += 1
        return {"size": len(await request.body())}

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)):
        calls["count"] += 1
        return {"size": len(await file.read())}

    @app.get("/empty")
    async def empty():
        return {"ok": True}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client


async def _send(client, path, content_length, **kwargs):
    request = client.build_request("POST", path, **kwargs)
    request.headers["Content-Length"] = content_length
    return await client.send(request)


def _assert_error(response, status_code, error_code):
    assert response.status_code == status_code
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == error_code


# --- Accepted requests ---


@pytest.mark.parametrize("size", [_MAX_BYTES - 1, _MAX_BYTES], ids=["under", "at"])
async def test_body_within_limit_reaches_route_intact(client, size):
    response = await client.post("/raw", content=b"x" * size)

    assert response.status_code == 200
    assert response.json() == {"size": size}


async def test_request_without_body_passes(client):
    response = await client.get("/empty")

    assert response.status_code == 200


# --- Content-Length check ---


async def test_content_length_over_limit_is_rejected_before_route(client, calls):
    response = await client.post("/raw", content=b"x" * (_MAX_BYTES + 1))

    _assert_error(response, 413, "FILE_SIZE_LIMIT_EXCEEDED")
    assert calls["count"] == 0


@pytest.mark.parametrize(
    "content_length",
    ["abc", "-5", "²"],
    ids=["not-a-number", "negative", "non-ascii-digit"],
)
async def test_malformed_content_length_is_rejected(client, calls, content_length):
    response = await _send(client, "/raw", content_length, content=b"x")

    _assert_error(response, 400, "INVALID_CONTENT_LENGTH")
    assert calls["count"] == 0


async def test_chunked_request_is_rejected(client, calls):
    async def body():
        yield b"x"

    response = await client.post("/raw", content=body())

    _assert_error(response, 411, "CONTENT_LENGTH_REQUIRED")
    assert calls["count"] == 0


# --- Streamed body check ---


@pytest.mark.parametrize(
    "path, kwargs",
    [
        ("/raw", {"content": b"x" * (_MAX_BYTES * 2)}),
        ("/upload", {"files": {"file": ("a.txt", b"x" * (_MAX_BYTES * 2))}}),
    ],
    ids=["raw-body", "multipart-upload"],
)
async def test_body_larger_than_declared_is_rejected_while_read(client, path, kwargs):
    response = await _send(client, path, "10", **kwargs)

    _assert_error(response, 413, "FILE_SIZE_LIMIT_EXCEEDED")


async def test_non_http_scope_is_passed_through():
    downstream = AsyncMock()
    middleware = RequestSizeLimitMiddleware(downstream)
    scope = {"type": "lifespan"}
    receive, send = AsyncMock(), AsyncMock()

    await middleware(scope, receive, send)

    downstream.assert_awaited_once_with(scope, receive, send)
