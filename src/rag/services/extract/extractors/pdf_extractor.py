import logging
from collections.abc import Iterator
from pathlib import Path

import pymupdf

from src.exceptions import unprocessable_content_error
from src.rag.services.extract.extractors.extractor import Extractor, Segment

_logger = logging.getLogger(__name__)


class PdfExtractor(Extractor):
    """Text extractor for PDF documents."""

    def extract(self, path: Path) -> Iterator[Segment]:
        try:
            document = pymupdf.open(str(path))
        except Exception as exc:
            _logger.warning("Could not open the PDF file: %s", path.name)
            raise unprocessable_content_error(
                message="The PDF file is corrupt or unreadable.",
                error_code="PDF_EXTRACTION_ERROR",
            ) from exc

        found = False
        failed_pages = 0

        with document:
            if document.needs_pass:
                raise unprocessable_content_error(
                    message="The PDF file is password protected.",
                    error_code="PDF_ENCRYPTED",
                )

            if document.is_repaired:
                # A damaged file can lose pages without raising any error.
                _logger.warning(
                    "The PDF file '%s' was damaged and repaired on open. "
                    "Some pages may be missing.",
                    path.name,
                )

            page_count = document.page_count

            for page_number in range(1, page_count + 1):
                try:
                    page = document.load_page(page_number - 1)
                    # NUL characters are valid in a PDF but cannot be stored
                    # in a PostgreSQL text column.
                    text = page.get_text("text").replace("\x00", "").strip()
                except Exception:
                    failed_pages += 1
                    _logger.warning(
                        "Skipping page %d of the PDF file '%s' due to "
                        "an extraction error",
                        page_number,
                        path.name,
                    )
                    continue

                if text:
                    found = True
                    yield Segment(text=text, page=page_number)

        if not found:
            if 0 < page_count == failed_pages:
                raise unprocessable_content_error(
                    message="Every page of the PDF failed to extract.",
                    error_code="PDF_EXTRACTION_ERROR",
                )

            raise unprocessable_content_error(
                message="The PDF contains no readable text.",
                error_code="PDF_NO_CONTENT",
            )
