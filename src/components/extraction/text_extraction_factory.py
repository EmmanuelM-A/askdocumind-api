"""
Factory for creating text document extractors based on file type.
"""

from pathlib import Path

from src.components.extraction.base_extractor import TextDocumentExtractor
from src.components.extraction.text_extractor import (
    PDFDocumentExtractor,
    DocxDocumentExtractor,
    MarkdownDocumentExtractor,
    TxtDocumentExtractor,
)

_extractors: dict[str, type[TextDocumentExtractor]] = {
    "pdf": PDFDocumentExtractor,
    "docx": DocxDocumentExtractor,
    "markdown": MarkdownDocumentExtractor,
    "txt": TxtDocumentExtractor,
    "md": MarkdownDocumentExtractor,
}


def get_text_extractor(filename: str) -> TextDocumentExtractor:
    """
    Retrieves text extractor based on file type.

    :param filename: The filename of the text document.
    :return: The text extractor instance corresponding to the file type.
    :raises ValueError: If the file type is not supported.
    """
    suffix = Path(filename).suffix.lower().lstrip(".")

    extractor_cls = _extractors.get(suffix)
    if extractor_cls is None:
        raise ValueError(f"Unsupported file type: {filename}")

    return extractor_cls()
