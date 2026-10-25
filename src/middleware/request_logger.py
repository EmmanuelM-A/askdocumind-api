"""
Pure ASGI middleware that logs one line per HTTP request.
"""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.middleware.utils import get_route_path

_logger = logging.getLogger(__name__)


class RequestLoggerMiddleware:
    """Logs method, path, status code, and duration for each request."""

    def __init__(
        self, app: ASGIApp, exclude_paths: frozenset[str] = frozenset()
    ) -> None:
        self.app = app
        self.exclude_paths = exclude_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or get_route_path(scope) in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            _logger.log(
                logging.ERROR if status_code >= 500 else logging.INFO,
                "%s %s | status: %s | %.1f ms",
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
            )
