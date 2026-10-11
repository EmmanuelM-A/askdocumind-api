import zipfile
from collections.abc import Iterator
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table, _Row
from docx.text.paragraph import Paragraph

from src.exceptions import unprocessable_content_error

from src.rag.services.extract.extractors.extractor import (
    Extractor,
    Segment,
    group_blocks,
)


def _heading_level(paragraph: Paragraph) -> int:
    style = paragraph.style.name if paragraph.style is not None else ""
    style = style or ""

    if style == "Title":
        return 1
    if style.startswith("Heading "):
        suffix = style.removeprefix("Heading ")
        if suffix.isdigit():
            return min(int(suffix), 6)
    return 0


def _row_text(row: _Row) -> str:
    cells: list[str] = []
    seen: list = []

    for cell in row.cells:
        # Merged cells repeat in row.cells, so skip any cell already read.
        if any(cell._tc is element for element in seen):
            continue
        seen.append(cell._tc)

        text = cell.text.strip()
        if text:
            cells.append(text)

    return " | ".join(cells)


def _blocks(document) -> Iterator[tuple[str, bool]]:
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue

            level = _heading_level(item)
            if level:
                yield f"{'#' * level} {text}", True
            else:
                yield text, False

        elif isinstance(item, Table):
            for row in item.rows:
                text = _row_text(row)
                if text:
                    yield text, False


class DocxExtractor(Extractor):
    """Text extractor for DOCX documents."""

    def extract(self, path: Path) -> Iterator[Segment]:
        try:
            document = Document(str(path))
        except (PackageNotFoundError, zipfile.BadZipFile, KeyError) as exc:
            raise unprocessable_content_error(
                message="The DOCX file is corrupt or unreadable.",
                error_code="DOCX_EXTRACTION_ERROR",
                cause=exc,
            ) from exc

        yield from group_blocks(_blocks(document))
