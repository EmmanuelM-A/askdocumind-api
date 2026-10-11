import logging
from collections.abc import Iterator
from pathlib import Path

import pymupdf

from src.exceptions import unprocessable_content_error

from .extractor import Extractor, Segment

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

        with document:
            if document.needs_pass:
                raise unprocessable_content_error(
                    message="The PDF file is password protected.",
                    error_code="PDF_ENCRYPTED",
                )

            for page_number, page in enumerate(document, start=1):
                try:
                    text = page.get_text("text").strip()
                except Exception:
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
            raise unprocessable_content_error(
                message="The PDF contains no readable text.",
                error_code="PDF_NO_CONTENT",
            )
