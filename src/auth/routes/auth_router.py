from typing import Annotated

from fastapi import APIRouter, Request, Depends, status
from starlette.responses import JSONResponse

from src.auth.dependencies import get_anonymous_user_service, get_cookie_config
from src.auth.services.anonymous_user_service import AnonymousUserService
from src.auth.services.cookie_service import set_cookie, CookieConfig
from src.config.configs import settings
from src.response.delivery import send_success_response

auth_router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@auth_router.post(
    path="/anonymous/init",
    summary="Initialize an anonymous user session",
)
async def init_anonymous_session(
    request: Request,
    anonymous_user_service: Annotated[
        AnonymousUserService, Depends(get_anonymous_user_service)
    ],
    cookie_config: Annotated[CookieConfig, Depends(get_cookie_config)],
) -> JSONResponse:
    """
    Initialize an anonymous user session. A valid token in the request cookies
    returns the existing user. Otherwise, a new anonymous user is created and
    a new token is set in the response cookies.
    """
    cookie_value = request.cookies.get(settings.auth.ANONYMOUS_COOKIE_NAME)

    user, token = await anonymous_user_service.init_anonymous_user(
        anonymous_token=cookie_value
    )

    response = send_success_response(
        message="Successfully initialized anonymous session",
        status_code=status.HTTP_200_OK,
        data=user,
    )

    set_cookie(
        response=response,
        cookie_name=settings.auth.ANONYMOUS_COOKIE_NAME,
        cookie_value=token,
        max_age_seconds=settings.auth.COOKIE_TTL_HOURS * 3600,
        path="/",
        config=cookie_config,
    )

    return response
