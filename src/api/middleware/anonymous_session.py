"""
Middleware that ensures each API request has a signed anonymous session.
"""

from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.api.services.auth.anonymous_identity import (
    reset_current_anonymous_user_id,
    set_current_anonymous_user_id,
)
from src.api.utils.cookie_manager import set_cookie
from src.api.utils.session_manager import get_token_manager
from src.config.configs import settings
from src.database.repository import get_database_repository
from src.database.repository.interfaces.user_repository import UpdatedUserData
from src.errors.custom_exceptions import unprocessable_entity_error, not_found_error


class AnonymousSessionMiddleware(BaseHTTPMiddleware):
    """
    Check if the cookie value for the session is valid and corresponds to an
    existing anonymous user.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:

        token_manager = get_token_manager()
        cookie_name = settings.auth.ANON_SESSION_USER_COOKIE_NAME
        cookie_value = request.cookies.get(cookie_name)
        user_repo = get_database_repository("USER")

        if not cookie_value:
            raise unprocessable_entity_error(
                message="No cookie value provided", error_code="NO_COOKIE_VALUE"
            )

        anonymous_id = token_manager.decode_token(cookie_value).user_id

        existing_user = await user_repo.get_by_id(anonymous_id)
        if existing_user is None:
            raise not_found_error(
                message="Anonymous session user no longer exists.",
                error_code="ANONYMOUS_USER_NOT_FOUND",
            )

        await user_repo.update(
            anonymous_id,
            UpdatedUserData(last_seen_at=datetime.now(timezone.utc).isoformat()),
        )

        request.state.anonymous_user_id = anonymous_id
        context_token = set_current_anonymous_user_id(anonymous_id)

        try:
            response = await call_next(request)
        finally:
            reset_current_anonymous_user_id(context_token)

        set_cookie(
            response=response,
            cookie_name=cookie_name,
            cookie_value=context_token,
            max_age_seconds=settings.auth.ANON_SESSION_COOKIE_AGE,
        )

        return response
