"""
Module for text extraction from various file formats.
"""

from importlib.metadata import PackageNotFoundError
import zipfile

try:
    import docx  # python-docx package
except ImportError:
    docx = None

import fitz
from fastapi import UploadFile

from src.components.extraction.base_extractor import TextDocumentExtractor
from src.components.ingestion.document import FileDocumentMetadata
from src.config.constants import Source
from src.errors.custom_exceptions import server_error
from src.logger.base_logger import BaseLogger

logger = BaseLogger(__name__)


class TxtDocumentExtractor(TextDocumentExtractor):
    """Text extractor for TXT documents."""

    def extract_text_from(self, document: UploadFile) -> str:
        try:
            content = document.file.read().decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                f"UTF-8 decoding failed, trying Latin-1 decoding for the file {document.filename}"
            )
            document.file.seek(0)
            content = document.file.read().decode("latin-1")
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{document.filename}",
                error_code="TEXT_EXTRACTION_ERROR",
                stack_trace=str(e),
            )

        return content

    def extract_metadata_from(self, document: UploadFile) -> FileDocumentMetadata:
        return FileDocumentMetadata(
            filename=document.filename,
            file_extension=".txt",
            author=None,
            source=Source.UPLOAD,
        )


class MarkdownDocumentExtractor(TextDocumentExtractor):
    """Text extractor for Markdown documents."""

    def extract_text_from(self, document: UploadFile) -> str:
        try:
            content = document.file.read().decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                f"UTF-8 decoding failed, trying Latin-1 decoding for the file {document.filename}"
            )
            document.file.seek(0)
            content = document.file.read().decode("latin-1")
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{document.filename}",
                error_code="MARKDOWN_EXTRACTION_ERROR",
                stack_trace=str(e),
            )

        return content

    def extract_metadata_from(self, document: UploadFile) -> FileDocumentMetadata:
        return FileDocumentMetadata(
            filename=document.filename,
            file_extension=".md",
            author=None,
            source=Source.UPLOAD,
        )


class PDFDocumentExtractor(TextDocumentExtractor):
    """Text extractor for PDF documents."""

    def extract_text_from(self, document: UploadFile) -> str:
        content = ""
        pdf_bytes = document.file.read()

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            if not doc:
                raise server_error(
                    message="PDF contains no readable content",
                    error_code="PDF_EXTRACTION_ERROR",
                )

            for page_num, page in enumerate(doc):
                try:
                    page_text = page.get_text("text")
                    if page_text.strip():
                        content += f"\n--- Page {page_num + 1} ---\n{page_text}"
                except Exception:
                    logger.warning(
                        f"Error extracting page {page_num + 1} of {document.filename}"
                    )
                    continue

            if not content.strip():
                raise server_error(
                    message="PDF contains no readable content",
                    error_code="PDF_NO_CONTENT",
                )

            return content.strip()

        finally:
            document.file.seek(0)

    def extract_metadata_from(self, document: UploadFile) -> FileDocumentMetadata:
        return FileDocumentMetadata(
            filename=document.filename,
            file_extension=".pdf",
            author=None,
            source=Source.UPLOAD,
        )


class DocxDocumentExtractor(TextDocumentExtractor):
    """Text extractor for DOCX documents."""

    def extract_text_from(self, document: UploadFile) -> str:
        if docx is None:
            raise server_error(
                message=(
                    "python-docx is not installed or an incompatible 'docx' package "
                    "is present. Please install the correct dependency: 'python-docx'."
                ),
                error_code="MISSING_PYTHON_DOCX",
            )

        try:
            document.file.seek(0)
            doc = docx.Document(document.file)
            content = "\n".join([para.text for para in doc.paragraphs])
            return content
        except (
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            OSError,
            PackageNotFoundError,
            zipfile.BadZipFile,
            MemoryError,
        ) as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{document.filename}",
                error_code="DOCX_EXTRACTION_ERROR",
                stack_trace=str(e),
            )

    def extract_metadata_from(self, document: UploadFile) -> FileDocumentMetadata:
        return FileDocumentMetadata(
            filename=document.filename,
            file_extension=".docx",
            author=None,
            source=Source.UPLOAD,
        )
