"""
Middleware that ensures each API request has a signed anonymous session.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from src.api.utils.session_identity import (
    get_anonymous_session_token_manager,
    reset_current_anonymous_user_id,
    set_current_anonymous_user_id,
    utc_now_naive,
)
from src.config.configs import settings
from src.database.connection import get_database_connection
from src.database.models import User
from src.database.repository.sqlalchemy import UserRepository
from src.database.repository.interfaces.user_repository import UpdatedUserData


class AnonymousSessionMiddleware(BaseHTTPMiddleware):
    """Resolve or create the anonymous session cookie for API requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        api_prefix = settings.server.API_V1_PREFIX.rstrip("/")
        if not (
            request.url.path == api_prefix
            or request.url.path.startswith(f"{api_prefix}/")
        ):
            return await call_next(request)

        token_manager = get_anonymous_session_token_manager()
        cookie_name = settings.auth.ANON_SESSION_COOKIE_NAME
        cookie_value = request.cookies.get(cookie_name)
        user_repo = UserRepository(connection=get_database_connection())
        now = utc_now_naive()

        refresh_cookie = False

        if cookie_value:
            try:
                payload = token_manager.decode_token(cookie_value)
                user_id = payload.user_id

                existing_user = await user_repo.get_by_id(user_id)
                if existing_user is None:
                    raise ValueError("Anonymous session user no longer exists.")

                await user_repo.update(
                    user_id,
                    UpdatedUserData(
                        last_seen_at=now.isoformat(),
                    ),
                )
            except Exception:
                user = User()
                user_id = await user_repo.create(user)
                refresh_cookie = True
        else:
            user = User()
            user_id = await user_repo.create(user)
            refresh_cookie = True

        request.state.anonymous_user_id = user_id
        context_token = set_current_anonymous_user_id(user_id)

        try:
            response = await call_next(request)
        finally:
            reset_current_anonymous_user_id(context_token)

        if settings.auth.ANON_SESSION_REFRESH_EVERY_REQUEST or refresh_cookie:
            session_token = token_manager.create_token(user_id)
            same_site = settings.auth.ANON_SESSION_COOKIE_SAMESITE.lower()
            secure = settings.auth.ANON_SESSION_COOKIE_SECURE or same_site == "none"
            response.set_cookie(
                key=cookie_name,
                value=session_token,
                httponly=settings.auth.ANON_SESSION_COOKIE_HTTP_ONLY,
                secure=secure,
                samesite=same_site,
                max_age=token_manager.ttl_seconds,
                path="/",
                domain=settings.auth.ANON_SESSION_COOKIE_DOMAIN,
            )

        return response
