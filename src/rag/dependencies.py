from typing import Annotated

from fastapi import Depends

from src.config.configs import settings
from src.database.dependencies import DbSession
from src.rag.repository.chunk_embedding_repository import ChunkEmbeddingRepository
from src.rag.repository.chunk_embedding_repository_impl import (
    ChunkEmbeddingRepositoryImpl,
)
from src.rag.services.chunk.factory import ChunkerBuildConfig, ChunkerFactory
from src.rag.services.embed.embedder import Embedder
from src.rag.services.embed.langchain_openai_embedder import LangChainOpenAIEmbedder
from src.rag.services.extract.extraction import Extraction
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.rag.services.report.document_status_reporter import DocumentStatusReporter
from src.rag.services.report.status_reporter import StatusReporter
from src.rag.services.store import StoreChunkEmbeddingService, RunGuard
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
