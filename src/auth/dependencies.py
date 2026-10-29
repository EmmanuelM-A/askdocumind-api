from typing import Annotated

from fastapi import Depends

from src.auth.repository.user_repository import UserRepository
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.services.anonymous_user_service import AnonymousUserService
from src.auth.services.cookie_service import CookieConfig
from src.config.configs import settings
from src.database.dependencies import DbSession


def get_user_repository(session: DbSession) -> UserRepository:
    """
    Provide a UserRepository bound to the current request's session.
    """
    return UserRepositoryImpl(session)


def get_anonymous_user_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> AnonymousUserService:
    """
    Provide an AnonymousUserService for the current request.
    """
    return AnonymousUserService(user_repository=user_repository)


def get_cookie_config() -> CookieConfig:
    """
    Provide the cookie settings for HTTP-only secure cookies.
    """
    return CookieConfig(
        http_only=True,
        secure=True,
        same_site="strict",
        domain=settings.auth.COOKIE_DOMAIN,
    )
