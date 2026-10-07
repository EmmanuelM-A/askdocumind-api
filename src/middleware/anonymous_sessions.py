"""
Middleware that ensures each API request has a signed anonymous session.
"""

import logging

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.auth.services.cookie_service import CookieConfig
from src.auth.services.token_service import decode_anonymous_token
from src.config.configs import settings
from src.auth.repository.user_repository import UserRepository
from src.response.delivery import send_error_response

_logger = logging.getLogger(__name__)


_EXCLUDED_PATHS = {
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/health",
}

_METHOD_SPECIFIC_EXCLUSIONS = {
    ("/auth/anonymous/init", "POST"),
}


def _is_excluded(request: Request) -> bool:
    path = request.url.path

    for method_specific_path, method in _METHOD_SPECIFIC_EXCLUSIONS:
        if path.endswith(method_specific_path) and request.method == method:
            return True

    return any(
        path == excluded or path.endswith(f"{excluded}/")
        for excluded in _EXCLUDED_PATHS
    )


class AnonymousSessionMiddleware(BaseHTTPMiddleware):
    """
    Check if the cookie value for the session is valid and corresponds to an
    existing anonymous user.
    """

    def __init__(self, app: ASGIApp, user_repository: UserRepository) -> None:
        super().__init__(app)
        self._user_repository = user_repository

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:

        if _is_excluded(request):
            return await call_next(request)

        cookie_value = request.cookies.get(settings.auth.COOKIE_NAME)

        if not cookie_value:
            return send_error_response(
                message="No anonymous session cookie found in the request.",
                status_code=status.HTTP_401_UNAUTHORIZED,
                error_code="ANONYMOUS_COOKIE_REQUIRED",
            )

        payload = decode_anonymous_token(token=cookie_value)

        existing_user = await self._user_repository.get_by_id(user_id=payload.user_id)

        if not existing_user:
            return send_error_response(
                message="Anonymous user not found for the provided session cookie.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="ANONYMOUS_USER_NOT_FOUND",
            )

        await self._user_repository.update_last_seen(
            user_id=payload.user_id, freq_mins=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS
        )

        _logger.debug(
            "Anonymous session validated for the user ID: '%s'}", payload.user_id
        )

        request.state.anonymous_user_id = payload.user_id

        return await call_next(request)
