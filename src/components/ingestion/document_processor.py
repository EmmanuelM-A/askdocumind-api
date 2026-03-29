"""
Memory-efficient document preprocessing pipeline for RAG systems.

This module is responsible for:
- Extracting text from uploaded files
- Validating and cleaning content
- Chunking text into smaller segments
- Streaming chunks one-by-one to downstream consumers

This implementation is optimized for large files and high concurrency.
"""

from typing import Iterator, List, Optional, Tuple
from fastapi import UploadFile

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.components.ingestion.document import FileDocument
from src.components.extraction.text_extraction_factory import get_extractor
from src.errors.custom_exceptions import unprocessable_entity_error
from src.config.configs import settings
from src.logger.base_logger import BaseLogger


class DocumentProcessor:
    """
    Document processor for memory-efficient RAG ingestion.

    This processor extracts, cleans, and chunks uploaded documents
    while yielding chunks incrementally instead of storing them in memory.

    Intended usage:
        for chunk in processor.process(files):
            embed(chunk.content)
            store(chunk)

    Guarantees:
    - Only one document is held in memory at a time
    - Only one chunk is yielded at a time
    - Suitable for large PDFs and many concurrent uploads
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
        self._logger = BaseLogger(__name__)

    def process(
        self,
        files: List[UploadFile | FileDocument],
    ) -> Iterator[FileDocument]:
        """
        Stream processed document chunks from uploaded files.

        Pipeline (per file):
            1. Select appropriate extractor
            2. Extract raw text + metadata
            3. Validate and clean content
            4. Split text into chunks
            5. Yield chunks immediately

        Args:
            files: List of uploaded files from the API request.

        Yields:
            FileDocument:
                - content: text chunk
                - metadata: inherited document metadata

        Raises:
            UnprocessableEntityError:
                If no valid chunks are produced from all files.
        """

        if not files:
            raise unprocessable_entity_error(
                message="No files provided for document processing.",
                error_code="NO_FILES_PROVIDED",
            )

        yielded_any_chunk = False

        for upload in files:
            self._logger.debug(f"Processing uploaded file: {upload.filename}")

            try:
                extractor = get_extractor(upload.filename)
            except ValueError:
                self._logger.warning(
                    f"Unsupported file type skipped: {upload.filename}"
                )
                continue

            # 1. Extract document (single document in memory)
            try:
                document = extractor.load_document(upload)
            except Exception as exc:
                self._logger.warning(
                    f"Failed to extract document {upload.filename}: {exc}"
                )
                continue

            # 2. Validate & clean
            success, cleaned_content = self._validate_document_content(
                document=document
            )

            if not success or not cleaned_content:
                self._logger.warning(f"Document validation failed: {upload.filename}")
                del document
                continue

            # 3. Chunk & stream
            for chunk_text in self.splitter.split_text(cleaned_content):
                if not chunk_text.strip():
                    continue

                yielded_any_chunk = True

                self._logger.debug(f"Yielding document chunk from {upload.filename}")

                yield FileDocument(
                    content=chunk_text,
                    metadata=document.metadata,
                )

            # 4. Explicit cleanup
            del document
            del cleaned_content

        if not yielded_any_chunk:
            raise unprocessable_entity_error(
                message="No valid document chunks produced.",
                error_code="NO_VALID_DOCUMENT_CHUNKS",
            )

    def _validate_document_content(
        self, document: FileDocument
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate document content before processing.

        Args:
            document: The FileDocument instance to validate.

        Returns:
            A tuple containing a boolean indicating if the document is valid,
            and the cleaned content or None.
        """

        if not document or not document.content:
            return False, None

        content = document.content.strip()
        if len(content) < settings.app.MIN_DOCUMENT_CONTENT_LENGTH:
            self._logger.warning(
                f"Document {document.metadata.filename} too short, skipping"
            )
            return False, None

        if len(content) > settings.app.MAX_DOCUMENT_CONTENT_LENGTH:
            if settings.app.IS_TRUNCATION_ENABLED:
                self._logger.warning(
                    f"Document {document.metadata.filename} too large, truncating"
                )
                document.content = (
                    content[: settings.app.MAX_DOCUMENT_CONTENT_LENGTH]
                    + "... [TRUNCATED]"
                )
            else:
                self._logger.warning(
                    f"Document {document.metadata.filename} too large, skipping"
                )
                return False, None

        return True, content
