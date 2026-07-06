import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer


@dataclass
class ChunkingConfig:
    max_tokens: int
    chunk_size: int
    chunk_overlap: int


class Chunker(ABC):
    """
    Abstract base class for document chunking.
    This class defines the interface for chunking documents into smaller pieces.
    """

    @abstractmethod
    async def chunk_document(self, document_content: str) -> List[str]:
        """Chunks the given document content into smaller pieces"""
        raise NotImplementedError("This method should be implemented by subclasses.")


class RecursiveCharacterChunker(Chunker):

    def __init__(self, config: ChunkingConfig):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

    async def chunk_document(self, document_content: str) -> List[str]:
        return self._splitter.split_text(document_content)


class DoclingHybirdChunker(Chunker):

    def __init__(self, config: ChunkingConfig):
        # Initialize tokenizer for token-aware chunking
        self._tokenizer = AutoTokenizer.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        self._chunker = HybridChunker(
            tokenizer=self._tokenizer, max_tokens=config.max_tokens, merge_peers=True
        )

    async def chunk_document(self, document_content: str) -> List[str]:
        """
        Chunks the given document content into smaller pieces using the Docling Hybrid Chunker.
        """

        def _chunk() -> List[str]:
            doc = DoclingDocument(name="document")
            doc.add_text(label=DocItemLabel.TEXT, text=document_content)

            chunks = self._chunker.chunk(doc)
            return [self._chunker.contextualize(chunk) for chunk in chunks]

        # Run the chunking in a separate thread to avoid blocking the event loop
        return await asyncio.to_thread(_chunk)
