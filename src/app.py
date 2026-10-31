"""
This module defines the FastAPI application instance and its configuration,
including middleware, routers, and exception handlers.

It also manages the database connection lifecycle using a lifespan
context manager.
"""

import asyncio
import logging
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
    get_downloader_service,
    get_embedder,
    get_extraction_service,
    get_status_reporter,
)
from src.rag.services.rerank.passthrough_reranker import PassthroughReranker
from src.rag.services.rerank.reranker import Reranker
from src.rag.services.utils import RunGuard
from src.uploads.routes.upload_router import upload_router
from src.uploads.services.ingestion_service import IngestionRunner
from src.uploads.services.sweeper import Sweeper, SweeperConfig
from src.uploads.storage.dependencies import get_object_storage

_logger = logging.getLogger(__name__)


async def _check_object_storage() -> None:
    try:
        await asyncio.to_thread(get_object_storage().check_available)
    except Exception:
        _logger.critical(
            "Object storage check failed: bucket '%s' at '%s' is missing or "
            "unreachable. Check S3_BUCKET_NAME, S3_ENDPOINT_URL and the S3 keys.",
            settings.uploads.S3_BUCKET_NAME,
            settings.uploads.S3_ENDPOINT_URL or "AWS S3",
        )
        raise


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
    await _check_object_storage()
    await session_manager.connect()

    runner = IngestionRunner(
        session_manager=session_manager,
        chunker_factory=get_chunker_factory(),
        extraction=get_extraction_service(get_downloader_service(get_object_storage())),
        embedder=get_embedder(),
        status_reporter=get_status_reporter(session_manager),
        guard=RunGuard(),
        max_concurrent=settings.uploads.MAX_CONCURRENT_UPLOADS,
    )
    sweeper = Sweeper(
        session_manager=session_manager,
        storage=get_object_storage(),
        runner=runner,
        config=SweeperConfig(interval_seconds=settings.uploads.SWEEPER_INTERVAL_SECS),
    )
    cleaner = ExpiredUserCleaner(
        session_manager=session_manager,
        storage=get_object_storage(),
        config=ExpiredUserCleanerConfig(
            interval_seconds=settings.auth.EXPIRED_USER_CLEANUP_INTERVAL_SECS
        ),
    )

    app.state.session_manager = session_manager
    app.state.ingestion_runner = runner

    sweeper.start()
    cleaner.start()

    reranker: Reranker
    if settings.rag.RERANKER_ENABLED:
        # Imported here so torch is only loaded when reranking is on
        from src.rag.services.rerank.cross_encoder_reranker import (
            CrossEncoderReranker,
            CrossEncoderRerankerConfig,
        )

        cross_encoder = CrossEncoderReranker(
            CrossEncoderRerankerConfig(
                model_name=settings.rag.RERANKER_MODEL_NAME,
                max_length=settings.rag.RERANKER_MAX_LENGTH,
                batch_size=settings.rag.RERANKER_BATCH_SIZE,
            )
        )
        await cross_encoder.warm_up()
        reranker = cross_encoder
    else:
        reranker = PassthroughReranker()
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

    # With a public URL, it's the only server listed. Without one, FastAPI
    # lists the relative root_path (/api), so local docs call the local host.
    servers = None
    if settings.server.API_PUBLIC_URL:
        servers = [
            {
                "url": settings.server.API_PUBLIC_URL,
                "description": settings.server.ENV.capitalize(),
            }
        ]

    app = FastAPI(
        title="AskDocuMind API",
        lifespan=lifespan,
        redirect_slashes=False,
        root_path="/api",
        docs_url="/docs",
        servers=servers,
        root_path_in_servers=servers is None,
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
    if settings.server.ENV == "production":
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
