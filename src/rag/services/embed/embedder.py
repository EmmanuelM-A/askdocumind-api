from abc import ABC
from typing import List

from src.rag.services.chunk.chunker import Chunk


class Embedder(ABC):
    """
    Defines the interface for the embedding service, which is responsible for
    converting text chunks into vector representations (embeddings).
    """

    async def embed_chunks(self, chunks: List[Chunk]) -> List[List[float]]:
        """
        Embed a list of chunks and return their embeddings.

        :param chunks: A list of Chunk objects to embed.
        :return: A list of embeddings, where each embedding is a list of floats.
        """
        raise NotImplementedError

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a query string and return its embedding.

        :param query: The query string to embed.
        :return: The embedding of the query as a list of floats.
        """
        raise NotImplementedError
