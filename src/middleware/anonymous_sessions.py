"""
Middleware which ensures each API request has a valid anonymous session.
"""

import logging

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.services.token_service import decode_anonymous_token
from src.config.configs import settings
from src.database.session import DatabaseSessionManager
from src.exceptions.base import ApiException
from src.middleware.utils import get_route_path
from src.response.delivery import send_error_response

_logger = logging.getLogger(__name__)

_INIT_PATH = "/v1/auth/anonymous/init"


def _unauthorized(error_code: str, message: str) -> JSONResponse:
    return send_error_response(
        message=message,
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_code=error_code,
    )


class AnonymousSessionMiddleware:
    """
    Requires a valid anonymous session cookie on every request except
    public paths, preflight requests, and the session init endpoint.
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.app = app
        self._exclude_paths = exclude_paths

    def _is_excluded(self, scope: Scope) -> bool:
        path = get_route_path(scope)
        method = scope["method"]
        return (
            method == "OPTIONS"
            or path in self._exclude_paths
            or (method == "POST" and path == _INIT_PATH)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_excluded(scope):
            await self.app(scope, receive, send)
            return

        rejection = await self._authenticate(scope)

        if rejection is not None:
            await rejection(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _authenticate(scope: Scope) -> JSONResponse | None:
        """
        Return an error response, or None after storing the user ID.
        """
        cookie_value = Request(scope).cookies.get(settings.auth.ANONYMOUS_COOKIE_NAME)

        if not cookie_value:
            return _unauthorized(
                "ANONYMOUS_COOKIE_REQUIRED",
                "No anonymous session cookie found in the request.",
            )

        session_manager: DatabaseSessionManager = scope["app"].state["session_manager"]

        try:
            payload = decode_anonymous_token(token=cookie_value)

            async with session_manager.get_session() as session:
                user_repository = UserRepositoryImpl(session=session)

                user = await user_repository.get_by_id(user_id=payload.user_id)

                if user is None:
                    return _unauthorized(
                        "ANONYMOUS_USER_NOT_FOUND",
                        "Anonymous user not found for the provided session cookie.",
                    )

                await user_repository.update_last_seen(
                    user_id=payload.user_id,
                    freq_mins=settings.auth.UPDATE_LAST_SEEN_FREQ_MINS,
                )

        except ApiException as exc:
            return send_error_response(
                message=str(exc.detail),
                status_code=exc.status_code,
                error_code=exc.error_code,
                details=exc.error_details,
            )

        scope.setdefault("state", {})["user_id"] = payload.user_id

        _logger.debug("Anonymous session validated for user '%s'", payload.user_id)

        return None
