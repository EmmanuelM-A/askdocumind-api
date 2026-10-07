from fastapi import Depends

from src.auth.repository.user_repository import UserRepository
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.services.anonymous_user_service import AnonymousUserService
from src.auth.services.cookie_service import CookieConfig
from src.config.configs import settings
from src.database import (
    DatabaseSessionManager,
    get_session_manager,
    get_tx_factory,
    DBTransactionFactory,
)


def get_user_repository(
    session_manager: DatabaseSessionManager = Depends(get_session_manager),
    tx_factory: DBTransactionFactory = Depends(get_tx_factory),
) -> UserRepository:
    """
    Dependency function to provide an instance of UserRepository.
    """
    return UserRepositoryImpl(session_manager=session_manager, tx_factory=tx_factory)


def get_anonymous_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> AnonymousUserService:
    """
    Dependency function to provide an instance of AnonymousUserService.
    """
    return AnonymousUserService(user_repository=user_repository)


def get_cookie_config() -> CookieConfig:
    """
    Dependency function to provide a CookieConfig instance for HTTP-only
    secure cookies.
    """
    return CookieConfig(
        http_only=True,
        secure=True,
        same_site="strict",
        domain=settings.auth.COOKIE_DOMAIN,
    )
