"""
Integration tests for the ConcurrentRequestLimitMiddleware.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.middleware.concurrent_request_limit import ConcurrentRequestLimitMiddleware

pytestmark = pytest.mark.asyncio

_MAX = 2
_RETRY_AFTER = 5
_ROOT = "/api"
_PUBLIC_ROUTE = "/health/server"
_PUBLIC = f"{_ROOT}{_PUBLIC_ROUTE}"
_SLOW = f"{_ROOT}/slow"
_FAST = f"{_ROOT}/fast"
_BROKEN = f"{_ROOT}/broken"


class _Gate:
    """Holds slow requests in flight until released."""

    def __init__(self) -> None:
        self.entered = 0
        self.release = asyncio.Event()

    async def wait_for_entered(self, count: int) -> None:
        async with asyncio.timeout(2):
            while self.entered < count:
                await asyncio.sleep(0)


@pytest.fixture
def gate():
    return _Gate()


@pytest_asyncio.fixture
async def client(gate):
    app = FastAPI(redirect_slashes=False, root_path=_ROOT)
    app.add_middleware(
        ConcurrentRequestLimitMiddleware,
        max_concurrent_requests=_MAX,
        exclude_paths=frozenset({_PUBLIC_ROUTE}),
        retry_after_secs=_RETRY_AFTER,
    )

    async def hold():
        gate.entered += 1
        await gate.release.wait()
        return {"ok": True}

    app.add_api_route("/slow", hold)
    app.add_api_route(_PUBLIC_ROUTE, hold)

    @app.get("/fast")
    async def fast():
        return {"ok": True}

    @app.get("/broken")
    async def broken():
        raise RuntimeError("boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client


async def _fill(client, gate, path=_SLOW, count=_MAX):
    tasks = [asyncio.create_task(client.get(path)) for _ in range(count)]
    await gate.wait_for_entered(count)
    return tasks


async def _drain(gate, tasks):
    gate.release.set()
    return await asyncio.gather(*tasks)


# --- Core behaviour ---


async def test_sequential_requests_beyond_limit_succeed(client):
    for _ in range(_MAX * 3):
        response = await client.get(_FAST)
        assert response.status_code == 200


async def test_request_over_limit_is_rejected(client, gate):
    in_flight = await _fill(client, gate)

    response = await client.get(_FAST)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SERVER_BUSY"

    for result in await _drain(gate, in_flight):
        assert result.status_code == 200


async def test_burst_admits_exactly_the_limit(client, gate):
    tasks = [asyncio.create_task(client.get(_SLOW)) for _ in range(_MAX + 3)]
    await gate.wait_for_entered(_MAX)

    responses = await _drain(gate, tasks)

    codes = sorted(r.status_code for r in responses)
    assert codes == [200] * _MAX + [503] * 3


async def test_slots_are_released_after_requests_complete(client, gate):
    await _drain(gate, await _fill(client, gate))

    responses = await asyncio.gather(*(client.get(_FAST) for _ in range(_MAX)))

    assert all(r.status_code == 200 for r in responses)


async def test_slot_is_released_when_downstream_raises(client):
    for _ in range(_MAX + 1):
        assert (await client.get(_BROKEN)).status_code == 500

    assert (await client.get(_FAST)).status_code == 200


# --- Excluded requests ---


@pytest.mark.parametrize(
    "path",
    [_PUBLIC, _PUBLIC_ROUTE],
    ids=["public-path", "public-path-without-root"],
)
async def test_excluded_path_bypasses_limit_at_capacity(client, gate, path):
    in_flight = await _fill(client, gate)
    excluded = asyncio.create_task(client.get(path))
    await gate.wait_for_entered(_MAX + 1)

    responses = await _drain(gate, [*in_flight, excluded])

    assert all(r.status_code == 200 for r in responses)


async def test_excluded_requests_do_not_take_slots(client, gate):
    excluded = await _fill(client, gate, path=_PUBLIC)

    responses = await asyncio.gather(*(client.get(_FAST) for _ in range(_MAX)))

    assert all(r.status_code == 200 for r in responses)
    await _drain(gate, excluded)


async def test_non_http_scope_is_passed_through():
    downstream = AsyncMock()
    middleware = ConcurrentRequestLimitMiddleware(downstream, max_concurrent_requests=1)
    scope = {"type": "lifespan"}
    receive, send = AsyncMock(), AsyncMock()

    await middleware(scope, receive, send)

    downstream.assert_awaited_once_with(scope, receive, send)
