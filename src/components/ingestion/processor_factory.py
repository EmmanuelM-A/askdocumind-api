"""Factory helpers for lazily constructing ingestion processor singletons."""

from typing import TYPE_CHECKING

from src.database.repository import get_database_repository

if TYPE_CHECKING:
    from src.components.ingestion.document_processor import (
        UploadedDocumentProcessor,
        WebDocumentProcessor,
    )
    from src.components.ingestion.vector_processor import VectorProcessor


_upload_document_processor: "UploadedDocumentProcessor | None" = None
_web_document_processor: "WebDocumentProcessor | None" = None
_vector_processor: "VectorProcessor | None" = None


def get_upload_document_processor() -> "UploadedDocumentProcessor":
    """Return a singleton instance of the uploaded document processor."""
    global _upload_document_processor

    if _upload_document_processor is None:
        from src.components.ingestion.document_processor import UploadedDocumentProcessor

        _upload_document_processor = UploadedDocumentProcessor()

    return _upload_document_processor


def get_web_document_processor() -> "WebDocumentProcessor":
    """Return a singleton instance of the web document processor."""
    global _web_document_processor

    if _web_document_processor is None:
        from src.components.ingestion.document_processor import WebDocumentProcessor

        _web_document_processor = WebDocumentProcessor()

    return _web_document_processor


def get_vector_processor() -> "VectorProcessor":
    """Return a singleton instance of the vector processor."""
    global _vector_processor

    if _vector_processor is None:
        from src.components.ingestion.vector_processor import VectorProcessor
        from src.components.retrieval.embedder import Embedder

        _vector_processor = VectorProcessor(
            upload_document_processor=get_upload_document_processor(),
            web_document_processor=get_web_document_processor(),
            embedder=Embedder(),
            document_chunk_repository=get_database_repository("DOCUMENT_CHUNK"),
        )

    return _vector_processor
