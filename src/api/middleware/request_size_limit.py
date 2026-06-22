"""Middleware to reject requests whose body exceeds a configured size limit."""

from starlette import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.utils.api_responses import ErrorInfo, ErrorResponseModel
from src.api.utils.response_delivery import create_error_response
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)

_ERROR_RESPONSE = create_error_response(
    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    error_response_model=ErrorResponseModel(
        message="Request body too large.",
        error=ErrorInfo(code="REQUEST_TOO_LARGE"),
    ),
)


class RequestSizeLimitMiddleware:
    """
    Rejects HTTP requests whose body exceeds max_body_size_bytes.

    Two-stage check:
    1. Content-Length header: immediate rejection before any body is read.
    2. Streaming fallback: buffers chunk-by-chunk for requests without Content-Length.
    """

    def __init__(self, app: ASGIApp, max_body_size_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_body_size_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if await self._is_oversized(scope, receive, send):
            return

        await self.app(scope, receive, send)

    async def _is_oversized(self, scope: Scope, receive: Receive, send: Send) -> bool:
        # Stage 1: reject immediately if Content-Length header already exceeds the limit.
        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")

        if content_length_raw is not None:
            try:
                if int(content_length_raw) <= self.max_bytes:
                    return False
            except ValueError:
                return False

            _logger.warning(
                f"Request rejected: Content-Length {content_length_raw.decode()} "
                f"exceeds limit {self.max_bytes} bytes"
            )
            await _ERROR_RESPONSE(scope, receive, send)
            return True

        # Stage 2: buffer chunk-by-chunk for chunked / no-Content-Length requests.
        total_bytes = 0
        chunks: list[bytes] = []

        while True:
            message = await receive()

            if message["type"] != "http.request":
                await self.app(scope, lambda: message, send)  # type: ignore[arg-type]
                return False

            chunk = message.get("body", b"")
            total_bytes += len(chunk)

            if total_bytes > self.max_bytes:
                _logger.warning(
                    f"Request rejected: streamed body exceeded limit {self.max_bytes} bytes",
                )
                await _ERROR_RESPONSE(scope, receive, send)
                return True

            chunks.append(chunk)

            if not message.get("more_body", False):
                break

        # Replay the buffered body to the app via the original receive callable.
        full_body = b"".join(chunks)
        consumed = False

        async def replay_receive() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
        return False
