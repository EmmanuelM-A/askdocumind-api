from abc import ABC, abstractmethod

from sentence_transformers import CrossEncoder

from src.config.configs import settings
from src.database.models import DocumentChunk
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


class Reranker(ABC):
    """
    Abstract base class for rerankers. Rerankers are responsible for reordering a list of document
    chunks based on their relevance to a given query.
    """

    @abstractmethod
    async def rerank(
        self, query: str, chunks: list[DocumentChunk], top_k: int
    ) -> list[DocumentChunk]:
        raise NotImplementedError("Subclasses must implement the rerank method.")


class CrossEncoderReranker(Reranker):
    """
    Reranker that uses a cross-encoder model to score and rerank document chunks based on their
    relevance to a given query.
    """

    def __init__(self):
        self.reranker: CrossEncoder | None = None

    def _initailize_reranker(self):
        if self.reranker is None:
            _logger.debug("Loading cross-encoder model for re-ranking...")
            self.reranker = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                max_length=settings.vector.MAX_TOKENS,
            )
            _logger.info("Cross-encoder loaded")

    async def rerank(
        self, query: str, chunks: list[DocumentChunk], top_k: int
    ) -> list[DocumentChunk]:
        self._initailize_reranker()

        assert self.reranker is not None, "Reranker model is not initialized."

        pairs = [[query, row.chunk_text] for row in chunks]
        scores = self.reranker.predict(pairs)

        # Combine chunks with their scores
        ranked_chunks = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[
            :top_k
        ]

        return [chunk for chunk, _ in ranked_chunks]
