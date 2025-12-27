"""
Factory for creating text document extractors based on file type.
"""

from src.components.extraction.base_extractor import TextDocumentExtractor
from src.components.extraction.text_extractor import (
    PDFDocumentExtractor,
    DocxDocumentExtractor,
    MarkdownDocumentExtractor,
    TxtDocumentExtractor,
)


def get_extractor(filename: str) -> TextDocumentExtractor:
    """
    Factory method to get the appropriate text document extractor.

    Args:
        filename: The filename of uploaded file for which to get the extractor.

    Returns:
        An instance of a TextDocumentExtractor suitable for the file type.
    """

    suffix = filename.lower()

    if suffix.endswith(".pdf"):
        return PDFDocumentExtractor()

    if suffix.endswith(".docx"):
        return DocxDocumentExtractor()

    if suffix.endswith(".md"):
        return MarkdownDocumentExtractor()

    if suffix.endswith(".txt"):
        return TxtDocumentExtractor()

    raise ValueError(f"Unsupported file type: {filename}")
