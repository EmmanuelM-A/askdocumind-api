"""
Middleware that ensures each API request has a signed anonymous session.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.api.utils.cookie_manager import set_cookie
from src.api.utils.session_manager import get_token_manager
from src.config.configs import settings
from src.database.repository import get_database_repository
from src.database.repository.sqlalchemy.user_repository import UserRepository
from src.errors.custom_exceptions import not_found_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class AnonymousSessionMiddleware(BaseHTTPMiddleware):
    """
    Check if the cookie value for the session is valid and corresponds to an
    existing anonymous user.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        current_path = request.url.path

        if request.method == "OPTIONS" or not current_path.startswith("/api/"):
            return await call_next(request)

        if current_path.startswith("/api/auth/anonymous"):
            return await call_next(request)

        if current_path.startswith("/api/health"):
            return await call_next(request)
        
        _logger.debug(f"Processing request for path: {current_path}")

        cookie_value = request.cookies.get(settings.auth.COOKIE_NAME)

        if not cookie_value:
            raise unprocessable_entity_error(
                message="No cookie value provided",
                error_code="NO_COOKIE_VALUE",
            )

        anonymous_id = get_token_manager().decode_token(cookie_value).user_id
        
        user_repo: UserRepository = get_database_repository("USER") # type: ignore

        existing_user = await user_repo.get_by_id(anonymous_id)
        if existing_user is None:
            raise not_found_error(
                message=f"Anonymous session user with ID {anonymous_id} not found.",
                error_code="ANONYMOUS_USER_NOT_FOUND",
            )

        await user_repo.update_last_seen(user_id=anonymous_id)
        
        _logger.debug(f"Anonymous session validated for user ID: {anonymous_id}")

        request.state.anonymous_user_id = anonymous_id
        
        response = await call_next(request)

        set_cookie(
            response=response,
            cookie_name=settings.auth.COOKIE_NAME,
            cookie_value=get_token_manager().create_token(anonymous_id),
            max_age_seconds=get_token_manager().ttl_seconds,
        )

        return response
