"""
This module defines the FastAPI application instance for the RAG Microservice.
It sets up the application with middleware, routers, exception handlers,
and a lifespan context manager for database connection management.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.auth.routes.auth_router import auth_router
from src.config.configs import settings
from src.config.paths import PUBLIC_PATHS
from src.database import get_session_manager, get_tx_factory
from src.exceptions import setup_exception_handlers
from src.health.router import health_check_router
from src.middleware.anonymous_sessions import AnonymousSessionMiddleware
from src.middleware.concurrent_request_limit import ConcurrentRequestLimitMiddleware
from src.middleware.request_logger import RequestLoggerMiddleware
from src.middleware.request_size_limit import RequestSizeLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application responsible for
    connecting to the database on startup and disconnecting on shutdown.
    """

    # On startup
    await get_session_manager().connect()

    yield

    # On shutdown
    await get_session_manager().disconnect()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.
    """
    app = FastAPI(
        title="RAG Microservice",
        lifespan=lifespan,
        redirect_slashes=False,
        root_path="/api",
    )

    # --- Middleware ---
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        AnonymousSessionMiddleware,
        user_repository=UserRepositoryImpl(
            session_manager=get_session_manager(), tx_factory=get_tx_factory()
        ),
        exclude_paths=PUBLIC_PATHS,
    )
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_size_bytes=settings.server.MAX_BODY_BYTES,
    )
    app.add_middleware(
        ConcurrentRequestLimitMiddleware,
        max_concurrent_requests=settings.server.MAX_CONCURRENT_REQUESTS,
        exclude_paths=PUBLIC_PATHS,
    )
    app.add_middleware(RequestLoggerMiddleware, exclude_paths=PUBLIC_PATHS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.CORS_ORIGINS,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,
    )

    # --- Routers ---
    app.include_router(router=health_check_router)
    app.include_router(prefix="/v1", router=auth_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)

    return app
