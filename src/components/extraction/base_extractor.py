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

    @abstractmethod
    def extract_metadata_from(self, document: UploadFile) -> FileDocumentMetadata:
        """
        Extracts metadata from the uploaded document.

        :param document: The UploadFile to extract metadata from.
        :return: The extracted metadata as a FileDocumentMetadata object.
        """

        raise NotImplementedError("Subclasses must implement this method.")

    def load_document(self, document: UploadFile) -> FileDocument:
        """
        Loads the document and returns a FileDocument object containing
        the extracted text and metadata.

        :param document: The UploadFile to load.
        :return: A FileDocument object with content and metadata.
        """

        # TODO SOME VALIDATION

        content = self.extract_text_from(document)
        metadata = self.extract_metadata_from(document)

        return FileDocument(content=content, metadata=metadata)
