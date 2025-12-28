"""
This module initializes the FastAPI application and includes the routes for
the application.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.chat_session_routes import chat_session_router
from src.api.routes.document_uploads_routes import document_upload_router
from src.api.routes.rag_chatbot_routes import rag_chatbot_router
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
    app.include_router(prefix="/api/v1", router=health_check_router)
    app.include_router(prefix="/api/v1", router=document_upload_router)
    app.include_router(prefix="/api/v1", router=chat_session_router)
    app.include_router(prefix="/api/v1", router=rag_chatbot_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)

    return app
