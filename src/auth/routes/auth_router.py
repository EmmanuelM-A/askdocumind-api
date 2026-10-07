from fastapi import APIRouter, Request, Depends, Response, status
from starlette.responses import JSONResponse

from src.auth.dependency import get_anonymous_user_service, get_cookie_config
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
    summary="Initialize an anonymous session",
)
async def init_anonymous_session(
    request: Request,
    response: Response,
    anonymous_user_service: AnonymousUserService = Depends(get_anonymous_user_service),
    cookie_config: CookieConfig = Depends(get_cookie_config),
) -> JSONResponse:
    """
    Initialize an anonymous session for the user. If a valid anonymous token
    is provided in the request cookies, it will return the existing user;
    otherwise, it will create a new anonymous user and return their details
    along with a new anonymous token set in the response cookies.
    """
    cookie_value: str | None = request.cookies.get(settings.auth.COOKIE_NAME)

    user, token = await anonymous_user_service.init_anonymous_user(
        anonymous_token=cookie_value
    )

    set_cookie(
        response=response,
        cookie_name=settings.auth.ANONYMOUS_COOKIE_NAME,
        cookie_value=token,
        max_age_seconds=settings.auth.COOKIE_TTL_HOURS * 3600,
        path="/anonymous/init",
        config=cookie_config,
    )

    return send_success_response(
        message="Successfully initialized anonymous session",
        status_code=status.HTTP_200_OK,
        data=user,
    )
