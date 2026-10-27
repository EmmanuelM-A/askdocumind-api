"""
This module defines the FastAPI application instance and its configuration,
including middleware, routers, and exception handlers.

It also manages the database connection lifecycle using a lifespan
context manager.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.auth.routes.auth_router import auth_router
from src.chat_session.routes.chat_session_router import chat_session_router
from src.chatbot.routes.chatbot_router import chatbot_router
from src.cleanup.expired_user_cleaner import (
    ExpiredUserCleaner,
    ExpiredUserCleanerConfig,
)
from src.config.configs import settings
from src.config.logger import setup_logging
from src.config.paths import PUBLIC_PATHS
from src.database.dependencies import DbSession
from src.database.session import DatabaseSessionManager
from src.exceptions.handlers import setup_exception_handlers
from src.health.router import health_check_router
from src.middleware.anonymous_sessions import AnonymousSessionMiddleware
from src.middleware.concurrent_request_limit import ConcurrentRequestLimitMiddleware
from src.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from src.middleware.request_logger import RequestLoggerMiddleware
from src.middleware.request_size_limit import RequestSizeLimitMiddleware
from src.rag.dependencies import (
    get_chunker_factory,
    get_extraction_service,
    get_downloader_service,
    get_embedder,
    get_status_reporter,
)
from src.rag.services.rerank.cross_encoder_reranker import (
    CrossEncoderReranker,
    CrossEncoderRerankerConfig,
)
from src.rag.services.utils import RunGuard
from src.uploads.dependencies import get_document_repository
from src.uploads.routes.upload_router import upload_router
from src.uploads.storage.dependencies import get_object_storage
from src.uploads.services.ingestion_service import IngestionRunner
from src.uploads.services.sweeper import Sweeper, SweeperConfig


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

    runner = IngestionRunner(
        session_manager=session_manager,
        chunker_factory=get_chunker_factory(),
        extraction=get_extraction_service(get_downloader_service(get_object_storage())),
        embedder=get_embedder(),
        status_reporter=get_status_reporter(get_document_repository(DbSession)),
        guard=RunGuard(),
        max_concurrent=settings.uploads.MAX_CONCURRENT_UPLOADS,
    )
    sweeper = Sweeper(
        session_manager=session_manager,
        storage=get_object_storage(),
        runner=runner,
        config=SweeperConfig(),
    )
    cleaner = ExpiredUserCleaner(
        session_manager=session_manager,
        storage=get_object_storage(),
        config=ExpiredUserCleanerConfig(),
    )

    app.state.session_manager = session_manager
    app.state.ingestion_runner = runner

    sweeper.start()
    cleaner.start()

    reranker = CrossEncoderReranker(
        CrossEncoderRerankerConfig(
            model_name=settings.rag.RERANKER_MODEL_NAME,
            max_length=settings.rag.RERANKER_MAX_LENGTH,
            batch_size=settings.rag.RERANKER_BATCH_SIZE,
        )
    )
    await reranker.warm_up()
    app.state.reranker = reranker

    try:
        yield
    finally:
        await cleaner.stop()
        await sweeper.stop()
        await runner.shutdown()
        await session_manager.disconnect()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.
    """
    setup_logging()

    app = FastAPI(
        title="AskDocuMind API",
        lifespan=lifespan,
        redirect_slashes=False,
        root_path="/api",
    )

    # SlowAPI's middleware and route decorators read the limiter from here
    app.state.limiter = limiter

    # --- Middleware ---
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        AnonymousSessionMiddleware,
        exclude_paths=PUBLIC_PATHS,
    )
    app.add_middleware(RequestSizeLimitMiddleware)
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
    app.include_router(prefix="/v1", router=upload_router)
    app.include_router(prefix="/v1", router=chatbot_router)

    # --- Exception Handlers ---
    setup_exception_handlers(app)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    return app
