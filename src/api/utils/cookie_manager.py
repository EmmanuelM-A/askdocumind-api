from starlette.responses import Response

from src.config.configs import settings


def set_cookie(
    response: Response, cookie_name: str, cookie_value: any, max_age_seconds: int
) -> None:
    """
    Set the cookie value for the session cookie.
    """
    same_site = settings.auth.ANON_SESSION_COOKIE_SAMESITE.lower()
    secure = settings.auth.ANON_SESSION_COOKIE_SECURE or same_site == "none"
    response.set_cookie(
        key=cookie_name,
        value=cookie_value,
        httponly=True,
        secure=secure,
        samesite=same_site,
        max_age=max_age_seconds,
        path="/",
        domain=settings.auth.ANON_SESSION_COOKIE_DOMAIN,
    )


def clear_cookie(response: Response, cookie_name: str) -> None:
    """
    Clear the cookie value for the session cookie.
    """
    same_site = settings.auth.ANON_SESSION_COOKIE_SAMESITE.lower()
    secure = settings.auth.ANON_SESSION_COOKIE_SECURE or same_site == "none"
    response.delete_cookie(
        key=cookie_name,
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
        domain=settings.auth.ANON_SESSION_COOKIE_DOMAIN,
    )
