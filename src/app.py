"""
This module defines the FastAPI application instance and its configuration,
including middleware, routers, and exception handlers.

It also manages the database connection lifecycle using a lifespan
context manager.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from src.auth.routes.auth_router import auth_router
from src.chat_session.routes.chat_session_router import chat_session_router
from src.config.configs import settings
from src.config.paths import PUBLIC_PATHS
from src.database import DatabaseSessionManager
from src.exceptions import setup_exception_handlers
from src.health.router import health_check_router
from src.middleware.anonymous_sessions import AnonymousSessionMiddleware
from src.middleware.concurrent_request_limit import ConcurrentRequestLimitMiddleware
from src.middleware.request_logger import RequestLoggerMiddleware
from src.middleware.request_size_limit import RequestSizeLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application. It manages the
    database connection lifecycle, ensuring that the database session manager
    is connected on startup and disconnected on shutdown.
    """
    session_manager = DatabaseSessionManager(
        database_url=settings.database.DATABASE_URL.get_secret_value()
    )

    # On startup
    await session_manager.connect()

    # Makes the session manager available to other parts of the application
    app.state["session_manager"] = session_manager

    yield

    # On shutdown
    await session_manager.disconnect()


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
    app.include_router(prefix="/v1", router=chat_session_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)

    return app
