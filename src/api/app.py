"""
This module initializes the FastAPI application and includes the routes for
the application.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database.connection import get_database_connection
from src.api.routes.health_check_routes import health_check_router
from src.api.middleware.exception_handler import setup_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application responsible for
    connecting to the database on startup and disconnecting on shutdown.
    """

    # Startup
    await get_database_connection().connect()
    yield

    # Shutdown
    await get_database_connection().disconnect()


def create_app():
    """Create and configure the FastAPI application."""

    app = FastAPI(title="DocuChatAPI", version="1.0.0", lifespan=lifespan)

    # --- Routers ---
    app.include_router(prefix="/api", router=health_check_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)

    return app
