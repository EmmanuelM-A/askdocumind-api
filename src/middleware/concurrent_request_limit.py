"""Middleware to cap the number of requests handled at the same time."""

import logging

from starlette import status
from starlette.types import ASGIApp, Receive, Scope, Send

from src.response.delivery import send_error_response

_logger = logging.getLogger(__name__)


class ConcurrentRequestLimitMiddleware:
    """
    Rejects HTTP requests with a 503 once max_concurrent_requests requests
    are in flight. The count is per process. Paths in exclude_paths bypass
    the limit and the count, so health probes always get an answer.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_concurrent_requests: int,
        exclude_paths: frozenset[str] = frozenset(),
        retry_after_secs: int = 1,
    ) -> None:
        self.app = app
        self._max = max_concurrent_requests
        self._exclude_paths = exclude_paths
        self._retry_after = str(retry_after_secs)
        self._active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self._exclude_paths:
            await self.app(scope, receive, send)
            return

        if self._active >= self._max:
            _logger.warning(
                "Request rejected: %s concurrent requests in flight", self._active
            )
            response = send_error_response(
                message="Server is busy. Please try again shortly.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                error_code="SERVER_BUSY",
                headers={"Retry-After": self._retry_after},
            )
            await response(scope, receive, send)
            return

        self._active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._active -= 1
