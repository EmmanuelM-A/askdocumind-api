from typing import Literal

from fastapi import Response
from pydantic import BaseModel


class CookieConfig(BaseModel):
    """
    Configuration for cookie settings.
    """

    http_only: bool
    secure: bool
    same_site: Literal["none", "strict", "lax"]
    domain: str | None = None


def set_cookie(
    response: Response,
    cookie_name: str,
    cookie_value: str,
    max_age_seconds: int,
    path: str,
    config: CookieConfig,
) -> None:
    """
    Set the cookie value for the session cookie.
    """
    response.set_cookie(
        key=cookie_name,
        value=cookie_value,
        httponly=config.http_only,
        secure=config.secure,
        samesite=config.same_site,
        max_age=max_age_seconds,
        path=path,
        domain=config.domain,
    )


def clear_cookie(
    response: Response, cookie_name: str, path: str, config: CookieConfig
) -> None:
    """
    Clear the cookie value for the session cookie.
    """
    response.delete_cookie(
        key=cookie_name,
        httponly=config.http_only,
        secure=config.secure,
        samesite=config.same_site,
        path=path,
        domain=config.domain,
    )
