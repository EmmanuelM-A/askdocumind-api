"""
Module for text extraction from various file formats.
"""

from abc import ABC, abstractmethod
from importlib.metadata import PackageNotFoundError
import zipfile
from io import BytesIO

try:
    import docx  # python-docx package
except ImportError:
    docx = None

import pymupdf

from src.errors.api_exceptions import ApiException
from src.errors.custom_exceptions import server_error
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class TextDocumentExtractor(ABC):
    """
    Abstract base class for text extractors.
    This class defines the interface for extracting data (text and metadata)
    from various file formats.
    """

    @abstractmethod
    def extract_text_from(self, data: bytes, filename: str) -> str:
        """
        Extracts the text data from the uploaded document.

        :param data: The UploadFile to extract data from.
        :param filename: The filename to extract data from.
        :return: The extracted text content as a string.
        """
        raise NotImplementedError("Subclasses must implement this method.")


class TxtDocumentExtractor(TextDocumentExtractor):
    """Text extractor for TXT documents."""

    def extract_text_from(self, data: bytes, filename: str) -> str:
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            _logger.warning(
                f"UTF-8 decoding failed, trying Latin-1 decoding for the file {filename}"
            )
            content = data.decode("latin-1")
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{filename}",
                error_code="TEXT_EXTRACTION_ERROR",
                stack_trace=str(e),
            )

        return content


class MarkdownDocumentExtractor(TextDocumentExtractor):
    """Text extractor for Markdown documents."""

    def extract_text_from(self, data: bytes, filename: str) -> str:
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            _logger.warning(
                f"UTF-8 decoding failed, trying Latin-1 decoding for the file {filename}"
            )
            content = data.decode("latin-1")
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{filename}",
                error_code="MARKDOWN_EXTRACTION_ERROR",
                stack_trace=str(e),
            )

        return content


class PDFDocumentExtractor(TextDocumentExtractor):
    """Text extractor for PDF documents."""

    def extract_text_from(self, data: bytes, filename: str) -> str:
        content = ""

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")

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
                    _logger.warning(
                        f"Error extracting page {page_num + 1} of {filename}"
                    )
                    continue

            if not content.strip():
                raise server_error(
                    message="PDF contains no readable content",
                    error_code="PDF_NO_CONTENT",
                )

            return content.strip()

        except ApiException:
            raise
        except Exception as e:
            raise server_error(
                message="An error occurred whilst extracting text from the file "
                f"{filename}",
                error_code="PDF_EXTRACTION_ERROR",
                stack_trace=str(e),
            )


class DocxDocumentExtractor(TextDocumentExtractor):
    """Text extractor for DOCX documents."""

    def extract_text_from(self, data: bytes, filename: str) -> str:
        if docx is None:
            raise server_error(
                message=(
                    "python-docx is not installed or an incompatible 'docx' package "
                    "is present. Please install the correct dependency: 'python-docx'."
                ),
                error_code="MISSING_PYTHON_DOCX",
            )

        try:
            file_stream = BytesIO(data)
            doc = docx.Document(file_stream)
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
                f"{filename}",
                error_code="DOCX_EXTRACTION_ERROR",
                stack_trace=str(e),
            )
