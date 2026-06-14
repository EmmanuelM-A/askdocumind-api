"""
Memory-efficient document preprocessing pipeline for RAG systems.

This module is responsible for:
- Extracting text from uploaded files
- Validating and cleaning content
- Chunking text into smaller segments
- Streaming chunks one-by-one to downstream consumers

This implementation is optimized for large files and high concurrency.
"""

from typing import Any, Iterator, List, Optional, Tuple, cast
from uuid import UUID

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.components.extraction.text_extraction_factory import get_text_extractor
from src.errors.custom_exceptions import unprocessable_entity_error
from src.config.configs import settings
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class DocumentProcessor:
    """
    Base class for document processors.
    """

    def __init__(self) -> None:
        """
        Initialize the streaming document processor with a recursive
        character-based text splitter.
        """
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.vector.CHUNK_SIZE,
            chunk_overlap=settings.vector.CHUNK_OVERLAP,
        )

    @staticmethod
    def _validate_content(
        content: str, filename: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate document content before processing, returning a tuple
        containing a boolean indicating if the document is valid and the
        cleaned content or None.
        """

        if not content:
            return False, None

        content = content.strip()
        if len(content) < settings.app.MIN_DOCUMENT_CONTENT_LENGTH:
            _logger.warning(f"Document {filename} too short, skipping")
            return False, None

        if len(content) > settings.app.MAX_DOCUMENT_CONTENT_LENGTH:
            if settings.app.IS_QUERY_TRUNCATION_ENABLED:
                _logger.warning(f"Document {filename} too large, truncating")
                content = (
                    content[: settings.app.MAX_DOCUMENT_CONTENT_LENGTH]
                    + "... [TRUNCATED]"
                )
            else:
                _logger.warning(f"Document {filename} too large, skipping")
                return False, None

        return True, content

    def _split_content(self, clean_content: str) -> list[str]:
        return self.splitter.split_text(clean_content)


class UploadedDocumentProcessor(DocumentProcessor):
    """
    Document processor for memory-efficient RAG ingestion from bytes.

    This processor extracts, cleans, and chunks uploaded documents
    while yielding chunks incrementally instead of storing them in memory.

    Intended usage:
        documents = [(filename, byte_data), ...]
        for chunk in processor.process(documents):
            embed(chunk)
            store(chunk)

    Guarantees:
    - Only one document is held in memory at a time
    - Only one chunk is yielded at a time
    - Suitable for large PDFs and many concurrent uploads
    """

    def __init__(self) -> None:
        super().__init__()

    def process(
        self,
        documents: List[Tuple[UUID, str, bytes]],
    ) -> Iterator[Tuple[UUID, str]]:
        """
        Stream processed document chunks from bytes.

        Pipeline (per document):
            1. Select appropriate extractor based on filename
            2. Extract raw text from bytes
            3. Validate and clean content
            4. Split text into chunks
            5. Yield chunks immediately

        Args:
            documents: List of (document_id, filename, bytes) tuples

        Yields:
            (document_id, cleaned chunk text) tuples
        """

        if not documents or len(documents) == 0:
            raise unprocessable_entity_error(
                message="No files provided for document processing.",
                error_code="NO_FILES_PROVIDED",
            )

        yielded_any_chunk = False

        for document_id, filename, data in documents:
            _logger.debug(f"Processing file: {filename}")

            extractor = get_text_extractor(filename)
            extractor_any = cast(Any, extractor)

            try:
                try:
                    document_content = extractor_any.extract_text_from(data, filename)
                except TypeError:
                    document_content = extractor_any.extract_text_from(data, filename)
            except Exception as exc:
                _logger.warning(f"Failed to extract document {filename}: {exc}")
                continue

            success, cleaned_content = self._validate_content(
                content=document_content, filename=filename
            )

            if not success or not cleaned_content:
                _logger.warning(f"Document validation failed: {filename}")
                del document_content
                continue

            for chunk_text in self._split_content(cleaned_content):
                if not chunk_text.strip():
                    continue

                yielded_any_chunk = True

                _logger.debug(f"Yielding document chunk from {filename}")

                yield document_id, chunk_text

        if not yielded_any_chunk:
            raise unprocessable_entity_error(
                message="No valid document chunks produced.",
                error_code="NO_VALID_DOCUMENT_CHUNKS",
            )


class WebDocumentProcessor(DocumentProcessor):

    def __init__(self) -> None:
        super().__init__()

    def process(
        self,
        raw_web_contents: List[str],
    ) -> Iterator[str]:
        """
        Processes raw web contents.
        """

        if not raw_web_contents or len(raw_web_contents) == 0:
            raise unprocessable_entity_error(
                message="No raw web contents provided for document processing.",
                error_code="NO_WEB_CONTENTS_PROVIDED",
            )

        yielded_any_chunk = False

        for raw_web_content in raw_web_contents:
            success, cleaned_web_content = self._validate_content(
                content=raw_web_content
            )

            if not success or not cleaned_web_content:
                _logger.warning("Raw web content validation failed")
                continue

            for chunked_text in self._split_content(cleaned_web_content):
                if not chunked_text.strip():
                    continue

                yielded_any_chunk = True

                _logger.debug("Yielding web content chunk")

                yield chunked_text

        if not yielded_any_chunk:
            raise unprocessable_entity_error(
                message="No valid document chunks produced.",
                error_code="NO_VALID_DOCUMENT_CHUNKS",
            )
