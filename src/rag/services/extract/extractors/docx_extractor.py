import zipfile
from collections.abc import Iterator
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from lxml.etree import LxmlError

from src.exceptions import unprocessable_content_error

from src.rag.services.extract.extractors.extractor import (
    Extractor,
    Segment,
    group_blocks,
)

# Guards against zip bombs. A small upload can expand to a huge XML part that
# python-docx would load fully into memory.
_MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024

_P = qn("w:p")
_TBL = qn("w:tbl")
_SDT = qn("w:sdt")
_SDT_CONTENT = qn("w:sdtContent")


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


def _iter_block_items(element, parent) -> Iterator[Paragraph | Table]:
    """
    Yield the paragraphs and tables inside `element` in document order.
    Content controls (w:sdt) are transparent, because python-docx skips
    everything inside them.
    """
    for child in element.iterchildren():
        if child.tag == _P:
            yield Paragraph(child, parent)
        elif child.tag == _TBL:
            yield Table(child, parent)
        elif child.tag == _SDT:
            content = child.find(_SDT_CONTENT)
            if content is not None:
                yield from _iter_block_items(content, parent)


def _cell_text(cell: _Cell) -> str:
    """Text of a cell, including any tables nested inside it."""
    parts: list[str] = []

    for item in _iter_block_items(cell._tc, cell):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                parts.append(text)
        else:
            parts.extend(_table_rows(item))

    return "\n".join(parts)


def _table_rows(table: Table) -> Iterator[str]:
    # Merged cells repeat in row.cells. A vertically merged cell repeats in
    # every row it spans, so the set is shared across the whole table.
    seen: set = set()

    for row in table.rows:
        cells: list[str] = []

        for cell in row.cells:
            if cell._tc in seen:
                continue
            seen.add(cell._tc)

            text = _cell_text(cell)
            if text:
                cells.append(text)

        if cells:
            yield " | ".join(cells)


def _blocks(document) -> Iterator[tuple[str, bool]]:
    for item in _iter_block_items(document.element.body, document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue

            level = _heading_level(item)
            if level:
                yield f"{'#' * level} {text}", True
            else:
                yield text, False

        else:
            for text in _table_rows(item):
                yield text, False


def _check_uncompressed_size(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError):
        return  # Document() reports unreadable files below.

    if total > _MAX_UNCOMPRESSED_BYTES:
        raise unprocessable_content_error(
            message="The DOCX file is too large once uncompressed.",
            error_code="DOCX_TOO_LARGE",
        )


class DocxExtractor(Extractor):
    """Text extractor for DOCX documents."""

    def extract(self, path: Path) -> Iterator[Segment]:
        _check_uncompressed_size(path)

        try:
            document = Document(str(path))
        except (
            PackageNotFoundError,
            zipfile.BadZipFile,
            KeyError,
            ValueError,
            LxmlError,
        ) as exc:
            raise unprocessable_content_error(
                message="The DOCX file is corrupt or unreadable.",
                error_code="DOCX_EXTRACTION_ERROR",
                cause=exc,
            ) from exc

        yield from group_blocks(_blocks(document))
