"""Middleware for header-based API version resolution."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.config.configs import settings


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Resolve API version from the Accept-Version header."""

    @staticmethod
    def _normalize_version(raw_version: str | None) -> str | None:
        if raw_version is None:
            return None

        version = raw_version.strip().lower()
        if version.startswith("v"):
            version = version[1:]

        return version or None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        if not path.startswith("/api/"):
            return await call_next(request)

        header_version = self._normalize_version(request.headers.get("Accept-Version"))

        requested_version = header_version or settings.app.DEFAULT_VERSION

        request.state.api_version = requested_version

        response = await call_next(request)

        response.headers["Content-Version"] = requested_version

        existing_vary = response.headers.get("Vary")

        if not existing_vary:
            response.headers["Vary"] = "Accept-Version"
        elif "accept-version" not in existing_vary.lower():
            response.headers["Vary"] = f"{existing_vary}, Accept-Version"

        return response
