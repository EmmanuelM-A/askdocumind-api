from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.embeddings import ChunkEmbedding
from src.storage.services import Chunk


@dataclass(slots=True)
class RerankedChunk:
    """
    Represents a chunk that has been reranked based on its relevance to a query.
    """

    chunk_embedding: ChunkEmbedding
    score: float


class Reranker(ABC):
    """
    Abstract base class for rerankers.
    """

    @abstractmethod
    async def rerank(
        self, query: str, chunk_embeddings: list[ChunkEmbedding]
    ) -> list[ChunkEmbedding]:
        """
        Reranks the given documents based on their relevance to the query.
        :param query: The query string to rerank the documents against.
        :param chunk_embeddings: The list of chunk embeddings to rerank.
        :return: The list of reranked chunks
        """
        raise NotImplementedError("Subclasses must implement this method.")
