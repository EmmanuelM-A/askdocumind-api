from typing import Annotated

from fastapi import Depends, Request

from src.auth.dependencies import get_user_repository
from src.auth.repository.user_repository import UserRepository
from src.chat_session.dependencies import get_chat_session_repository
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.config.configs import settings
from src.database.dependencies import DbSession, get_session_manager
from src.database.session import DatabaseSessionManager
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.rag.services.chunk.factory import ChunkerBuildConfig, ChunkerFactory
from src.rag.services.embed.embedder import Embedder
from src.rag.services.embed.langchain_openai_embedder import LangChainOpenAIEmbedder
from src.rag.services.expand.langchain_openai_expander import (
    LangChainOpenAIQueryExpander,
    QueryExpanderConfig,
)
from src.rag.services.expand.query_expander import QueryExpander
from src.rag.services.extract.extraction import Extraction
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.rag.services.fallback.brave_api_web_searcher import BraveAPIWebSearcher
from src.rag.services.fallback.web_searcher import WebSearcher
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.report.status_reporter import StatusReporter
from src.rag.services.rerank.reranker import Reranker
from src.rag.services.retrieve import RetrieveChunkEmbeddingService
from src.rag.services.store import StoreChunkEmbeddingService
from src.shared.prompts import load_prompt_from
from src.uploads.storage.dependencies import get_object_storage
from src.uploads.storage.object_storage import ObjectStorage


def get_chunk_embedding_repository(session: DbSession) -> ChunkEmbeddingRepository:
    """
    Provide a ChunkEmbeddingRepository bound to the current request's session.
    """
    return ChunkEmbeddingRepositoryImpl(session)


def get_downloader_service(
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> S3FileDownloader:
    """
    Provide an S3FileDownloader service instance for the current request.
    """
    return S3FileDownloader(object_storage)


def get_extraction_service(
    downloader: Annotated[S3FileDownloader, Depends(get_downloader_service)],
) -> Extraction:
    """
    Provide an Extraction service instance for the current request.
    """
    return Extraction(downloader=downloader, factory=ExtractorFactory())


def get_embedder() -> Embedder:
    """
    Provide an Embedder service instance for the current request.
    """
    return LangChainOpenAIEmbedder()


_chunker_build_config = ChunkerBuildConfig()  # TODO: Change later


def get_chunker_factory() -> ChunkerFactory:
    """
    Provide a ChunkerFactory instance for the current request.
    """
    return ChunkerFactory(config=_chunker_build_config)


def get_status_reporter(
    session_manager: Annotated[DatabaseSessionManager, Depends(get_session_manager)],
) -> StatusReporter:
    """
    Provide a StatusReporter instance for the current request.
    """
    return DocumentStatusReporter(session_manager)


def get_rag_storage_service(
    extraction: Annotated[Extraction, Depends(get_extraction_service)],
    chunker_factory: Annotated[ChunkerFactory, Depends(get_chunker_factory)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    chunk_embedding_repository: Annotated[
        ChunkEmbeddingRepository, Depends(get_chunk_embedding_repository)
    ],
    status_reporter: Annotated[StatusReporter, Depends(get_status_reporter)],
) -> StoreChunkEmbeddingService:
    """
    Provide a StoreChunkEmbeddingService instance for the current request.
    """
    return StoreChunkEmbeddingService(
        extraction=extraction,
        chunker_factory=chunker_factory,
        embedder=embedder,
        chunk_embedding_repository=chunk_embedding_repository,
        status_reporter=status_reporter,
    )


def get_query_expander() -> QueryExpander:
    """
    Provide a QueryExpander service instance for the current request.
    """
    return LangChainOpenAIQueryExpander(
        QueryExpanderConfig(
            prompt_template=load_prompt_from(
                path=settings.rag.EXPANSION_PROMPT_TEMPLATE
            )
        )
    )


def get_reranker(request: Request) -> Reranker:
    """
    Provide a Reranker service instance for the current request.
    """
    return request.app.state.reranker


def get_web_searcher() -> WebSearcher:
    return BraveAPIWebSearcher()


def get_rag_retrieval_service(
    query_expander: Annotated[QueryExpander, Depends(get_query_expander)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    web_searcher: Annotated[WebSearcher, Depends(get_web_searcher)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    chunk_embedding_repository: Annotated[
        ChunkEmbeddingRepository, Depends(get_chunk_embedding_repository)
    ],
    chat_session_repository: Annotated[
        ChatSessionRepository, Depends(get_chat_session_repository)
    ],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> RetrieveChunkEmbeddingService:
    return RetrieveChunkEmbeddingService(
        query_expander=query_expander,
        reranker=reranker,
        web_searcher=web_searcher,
        embedder=embedder,
        chunk_embedding_repository=chunk_embedding_repository,
        chat_session_repository=chat_session_repository,
        user_repository=user_repository,
    )
