"""
This module defines the FastAPI application instance for the RAG Microservice.
It sets up the application with middleware, routers, exception handlers,
and a lifespan context manager for database connection management.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.configs import settings
from src.database import get_session_manager
from src.exceptions import setup_exception_handlers
from src.health.router import health_check_router
from src.middleware.request_logger import RequestLoggerMiddleware
from src.middleware.request_size_limit import RequestSizeLimitMiddleware

_API_PREFIX = "/api/v1"


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
    app = FastAPI(title="RAG Microservice", lifespan=lifespan, redirect_slashes=False)

    # --- Middleware ---

    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,  # noqa: IGNORE
        allow_origins=settings.server.CORS_ORIGINS,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
        ],
        allow_credentials=True,
    )
    app.add_middleware(RequestLoggerMiddleware)

    # --- Routers ---
    app.include_router(prefix="/api", router=health_check_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)

    return app
