"""
This module initializes the FastAPI application and includes the routes for
the application.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.routes.chat_session_routes import chat_session_router
from src.api.routes.auth_routes import auth_router
from src.api.routes.document_uploads_routes import documents_router
from src.api.routes.rag_chatbot_routes import rag_chatbot_router
from src.api.services.cleanup.cleanup_resources import init_anon_user_sessions_cleanup
from src.config.configs import settings
from src.database.connection import get_database_connection
from src.api.middleware.anonymous_session import AnonymousSessionMiddleware
from src.api.middleware.handle_version import APIVersionMiddleware
from src.api.middleware.request_size_limit import RequestSizeLimitMiddleware
from src.api.routes.health_check_routes import health_check_router
from src.api.middleware.exception_handler import setup_exception_handlers
from src.api.middleware.rate_limiter import limiter


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """Delegate SlowAPI limit errors to the library-provided response builder."""
    return _rate_limit_exceeded_handler(request, exc)


API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application responsible for
    connecting to the database on startup and disconnecting on shutdown.
    """

    # Startup
    await get_database_connection().connect()
    cleanup_stop_event = asyncio.Event()

    cleanup_task = asyncio.create_task(
        init_anon_user_sessions_cleanup(stop_event=cleanup_stop_event)
    )

    yield

    # Shutdown
    cleanup_stop_event.set()
    if cleanup_task is not None:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task

    await get_database_connection().disconnect()


def _configure_third_party_loggers() -> None:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def create_app():
    """Create and configure the FastAPI application."""

    _configure_third_party_loggers()

    app = FastAPI(
        title="DocuChatAPI",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
        redirect_slashes=False,
    )
    app.state.limiter = limiter  # type: ignore[attr-defined]

    # --- Middleware ---
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_size_bytes=int(settings.server.MAX_REQUEST_BODY_SIZE_MB * 1024 * 1024),
    )
    app.add_middleware(APIVersionMiddleware)
    app.add_middleware(AnonymousSessionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.CORS_ORIGINS,
        allow_credentials=settings.server.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.server.CORS_ALLOW_METHODS,
        allow_headers=settings.server.CORS_ALLOW_HEADERS,
    )

    # --- Routers ---
    app.include_router(prefix=API_PREFIX, router=health_check_router)
    app.include_router(prefix=API_PREFIX, router=auth_router)
    app.include_router(prefix=API_PREFIX, router=documents_router)
    app.include_router(prefix=API_PREFIX, router=chat_session_router)
    app.include_router(prefix=API_PREFIX, router=rag_chatbot_router)

    # --- Exception Handlers ---
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)  # type: ignore[arg-type]
    setup_exception_handlers(app)

    return app
