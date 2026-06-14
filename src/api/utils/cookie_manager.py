from starlette.responses import Response

from src.config.configs import settings


def set_cookie(
    response: Response, cookie_name: str, cookie_value: any, max_age_seconds: int
) -> None:
    """
    Set the cookie value for the session cookie.
    """
    same_site = settings.auth.COOKIE_SAMESITE.lower()
    response.set_cookie(
        key=cookie_name,
        value=cookie_value,
        httponly=True,
        secure=same_site == "none",
        samesite=same_site, # type: ignore
        max_age=max_age_seconds,
        path="/",
        domain=settings.auth.COOKIE_DOMAIN,
    )


def clear_cookie(response: Response, cookie_name: str) -> None:
    """
    Clear the cookie value for the session cookie.
    """
    same_site = settings.auth.COOKIE_SAMESITE.lower()
    response.delete_cookie(
        key=cookie_name,
        httponly=True,
        secure=same_site == "none",
        samesite=same_site, # type: ignore
        path="/",
        domain=settings.auth.COOKIE_DOMAIN,
    )
