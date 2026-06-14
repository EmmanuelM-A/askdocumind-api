"""Controller for authentication-related endpoints."""

from typing import Optional

from fastapi import status
from fastapi import Request
from starlette.responses import JSONResponse

from src.api.services.auth.anonymous_user import AnonymousUserSessionService
from src.api.services.service_factory import get_anonymous_user_service
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.cookie_manager import set_cookie
from src.api.utils.response_delivery import create_success_response
from src.api.utils.session_manager import TokenManager, get_token_manager
from src.config.configs import settings
from src.logger.base_logger import BaseLogger


class AuthController:
    def __init__(self) -> None:
        self._anonymous_user_service: Optional[AnonymousUserSessionService] = None
        self._token_manager: Optional[TokenManager] = None
        self._logger = BaseLogger(__name__)

    def lazy_init(self) -> None:
        if self._anonymous_user_service is None:
            self._anonymous_user_service = get_anonymous_user_service()

        if self._token_manager is None:
            self._token_manager = get_token_manager()

    # ======================= ANONYMOUS USER SESSION =======================

    async def create_anonymous_user_endpoint(self, request: Request) -> JSONResponse:
        self.lazy_init()
        assert self._anonymous_user_service is not None
        assert self._token_manager is not None

        cookie_value = request.cookies.get(settings.auth.COOKIE_NAME)
        self._logger.info(
            "anonymous bootstrap request | "
            f"origin={request.headers.get('origin')} "
            f"method={request.method} "
            f"path={request.url.path} "
            f"cookie_found={bool(cookie_value)}"
        )

        anonymous_user_id = (
            await self._anonymous_user_service.init_anonymous_user_session(
                cookie_value=cookie_value
            )
        )

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
            cookie_name=settings.auth.COOKIE_NAME,
            cookie_value=self._token_manager.create_token(anonymous_user_id),
            max_age_seconds=self._token_manager.ttl_seconds,
        )
        self._logger.info(
            "anonymous bootstrap success | "
            f"origin={request.headers.get('origin')} "
            f"method={request.method} "
            f"path={request.url.path} "
            f"user_id={anonymous_user_id}"
        )
        return response
