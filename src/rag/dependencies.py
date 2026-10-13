from typing import Annotated

from fastapi import Depends

from src.chat_session.dependencies import get_chat_session_repository
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.config.configs import settings
from src.database.dependencies import DbSession
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.rag.services.chunk.factory import ChunkerBuildConfig, ChunkerFactory
from src.rag.services.delete import DeleteChunkEmbeddingService
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
from src.rag.services.fallback.web_searcher import WebSearcher
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.report.status_reporter import StatusReporter
from src.rag.services.rerank.reranker import Reranker
from src.rag.services.retrieve import RetrieveChunkEmbeddingService
from src.rag.services.store import StoreChunkEmbeddingService, RunGuard
from src.shared.prompts import load_prompt_from
from src.uploads.dependencies import get_document_repository
from src.uploads.repository.document_repository import DocumentRepository
from src.uploads.storage.object_storage import ObjectStorage


def get_chunk_embedding_repository(session: DbSession) -> ChunkEmbeddingRepository:
    """
    Provide a ChunkEmbeddingRepository bound to the current request's session.
    """
    return ChunkEmbeddingRepositoryImpl(session)


def get_downloader_service(
    object_storage: Annotated[ObjectStorage, Depends],
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
    document_repository: Annotated[
        DocumentRepository, Depends(get_document_repository)
    ],
) -> StatusReporter:
    """
    Provide a StatusReporter instance for the current request.
    """
    return DocumentStatusReporter(document_repository)


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
        guard=RunGuard(),
        max_concurrent=settings.rag.MAX_CONCURRENCY,
    )


def build_rag_storage_service(
    session: DbSession,
    extraction: Annotated[Extraction, Depends(get_extraction_service)],
    chunker_factory: Annotated[ChunkerFactory, Depends(get_chunker_factory)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    status_reporter: Annotated[StatusReporter, Depends(get_status_reporter)],
) -> StoreChunkEmbeddingService:
    """
    Provide a StoreChunkEmbeddingService instance for the current request.
    """
    return StoreChunkEmbeddingService(
        extraction=extraction,
        chunker_factory=chunker_factory,
        embedder=embedder,
        chunk_embedding_repository=get_chunk_embedding_repository(session),
        status_reporter=status_reporter,
        guard=RunGuard(),
        max_concurrent=settings.rag.MAX_CONCURRENCY,
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


def get_reranker() -> Reranker:
    pass


def get_web_searcher() -> WebSearcher:
    pass


def get_rag_retrieval_service() -> RetrieveChunkEmbeddingService:
    pass


def get_rag_deletion_service(
    chunk_embedding_repository: Annotated[
        ChunkEmbeddingRepository, Depends(get_chunk_embedding_repository)
    ],
    document_repository: Annotated[
        DocumentRepository, Depends(get_document_repository)
    ],
    chat_session_repository: Annotated[
        ChatSessionRepository, Depends(get_chat_session_repository)
    ],
) -> DeleteChunkEmbeddingService:
    """
    Provide a DeleteChunkEmbeddingService instance for the current request.
    """
    return DeleteChunkEmbeddingService(
        chunk_embedding_repo=chunk_embedding_repository,
        document_repository=document_repository,
        chat_session_repository=chat_session_repository,
    )
