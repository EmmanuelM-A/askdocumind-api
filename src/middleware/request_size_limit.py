"""
Middleware to reject requests whose body exceeds a configured size limit.
"""

import logging

from fastapi import status
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.config.configs import settings
from src.exceptions.base import ApiException
from src.response.delivery import send_error_response

_logger = logging.getLogger(__name__)

_MAX_REQUEST_BODY_SIZE = int(settings.server.MAX_REQUEST_BODY_SIZE_MB * 1024 * 1024)


class RequestSizeLimitMiddleware:
    """
    Rejects HTTP requests whose body exceeds max_body_size_bytes.

    Two checks run. The first reads the Content-Length header and rejects
    oversized requests before the app reads any data. The second counts bytes
    as the app reads the body, which covers requests with a missing or
    inaccurate Content-Length. Chunked transfer encoding is not accepted.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.max_bytes = _MAX_REQUEST_BODY_SIZE

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        is_chunked = "chunked" in headers.get("transfer-encoding", "").lower()

        if is_chunked:
            _logger.warning("Request rejected: chunked transfer encoding")
            response = send_error_response(
                message="Content-Length header is required.",
                status_code=status.HTTP_411_LENGTH_REQUIRED,
                error_code="CONTENT_LENGTH_REQUIRED",
            )
            await response(scope, receive, send)
            return

        if content_length is not None:
            if not (content_length.isascii() and content_length.isdigit()):
                _logger.warning(
                    "Request rejected: malformed Content-Length %r", content_length
                )
                response = send_error_response(
                    message="Content-Length header is invalid.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="INVALID_CONTENT_LENGTH",
                )
                await response(scope, receive, send)
                return

            if int(content_length) > self.max_bytes:
                _logger.warning(
                    "Request rejected: Content-Length %s exceeds limit %s bytes",
                    content_length,
                    self.max_bytes,
                )
                response = send_error_response(
                    message="Request body too large.",
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    error_code="FILE_SIZE_LIMIT_EXCEEDED",
                )
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    _logger.warning(
                        "Request rejected: body exceeded limit %s bytes",
                        self.max_bytes,
                    )
                    raise ApiException(
                        message="Request body too large.",
                        error_code="FILE_SIZE_LIMIT_EXCEEDED",
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    )
            return message

        await self.app(scope, limited_receive, send)
