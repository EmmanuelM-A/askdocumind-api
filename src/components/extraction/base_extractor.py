"""
Defines the abstract base class for text extractors.
"""

from abc import ABC, abstractmethod

from fastapi import UploadFile

from src.components.ingestion.document import FileDocumentMetadata, FileDocument


class TextDocumentExtractor(ABC):
    """
    Abstract base class for text extractors.
    This class defines the interface for extracting data (text and metadata)
    from various file formats.
    """

    @abstractmethod
    def extract_text_from(self, document: UploadFile) -> str:
        """
        Extracts the text data from the uploaded document.

        :param document: The UploadFile to extract data from.
        :return: The extracted text content as a string.
        """

        raise NotImplementedError("Subclasses must implement this method.")
