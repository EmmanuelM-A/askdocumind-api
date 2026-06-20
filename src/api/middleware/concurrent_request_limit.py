"""Middleware to cap the number of requests handled at the same time."""

from starlette import status
from starlette.types import ASGIApp, Receive, Scope, Send

from src.api.utils.api_responses import ErrorInfo, ErrorResponseModel
from src.api.utils.response_delivery import create_error_response

_ERROR_RESPONSE = create_error_response(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    error_response_model=ErrorResponseModel(
        message="Server is busy. Please try again shortly.",
        error=ErrorInfo(code="SERVER_BUSY"),
    ),
)


class ConcurrentRequestLimitMiddleware:
    """
    Rejects incoming HTTP requests once max_concurrent_requests active
    requests are already in flight.
    """

    def __init__(self, app: ASGIApp, max_concurrent_requests: int) -> None:
        self.app = app
        self._max = max_concurrent_requests
        self._active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._active >= self._max:
            await _ERROR_RESPONSE(scope, receive, send)
            return

        self._active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._active -= 1
