"""Controller for authentication-related endpoints."""

from fastapi import status
from fastapi import Request
from starlette.responses import JSONResponse

from src.api.services.service_factory import get_anonymous_user_service
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.cookie_manager import set_cookie
from src.api.utils.response_delivery import create_success_response
from src.api.utils.session_manager import get_token_manager
from src.config.configs import settings


class AuthController:
    def __init__(self) -> None:
        self.anonymous_user_service = None

    def lazy_init(self) -> None:
        if self.anonymous_user_service is None:
            self.anonymous_user_service = get_anonymous_user_service()

    # ======================= ANONYMOUS USER SESSION =======================

    async def create_anonymous_user_endpoint(self, request: Request) -> JSONResponse:
        self.lazy_init()

        cookie_name = settings.auth.ANON_SESSION_USER_COOKIE_NAME
        anonymous_user_id = (
            await self.anonymous_user_service.init_anonymous_user_session(
                request.cookies.get(cookie_name)
            )
        )
        token_manager = get_token_manager()

        response_model = SuccessResponseModel(
            message="Anonymous user session created successfully.",
            data={"user_id": str(anonymous_user_id)},
        )
        response = create_success_response(
            status_code=status.HTTP_201_CREATED,
            success_response_model=response_model,
        )

        set_cookie(
            response=response,
            cookie_name=cookie_name,
            cookie_value=token_manager.create_token(anonymous_user_id),
            max_age_seconds=token_manager.ttl_seconds,
        )
        return response
