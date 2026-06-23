"""Logs every incoming request with method, path, status, and duration."""

import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        _logger.info(
            f"{request.method} {request.url.path} "
            f"-> {response.status_code} "
            f"({duration_ms:.1f}ms)"
        )
        return response
