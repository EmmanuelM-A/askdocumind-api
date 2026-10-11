from pydantic import BaseModel
from sentence_transformers import CrossEncoder

from src.exceptions import unprocessable_content_error
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.services.rerank.reranker import Reranker
import logging

# TODO: add validation to config + tests for reranker


class CrossEncoderRerankerConfig(BaseModel):
    """
    Configuration for the CrossEncoderReranker.
    """

    model_name: str
    max_length: int
    batch_size: int = 32


_logger = logging.getLogger(__name__)


class CrossEncoderReranker(Reranker):
    """
    A reranker that uses a cross-encoder model to re-rank the retrieved chunks.
    """

    def __init__(self, config: CrossEncoderRerankerConfig) -> None:
        self._config = config
        self._model: CrossEncoder | None = None

    async def rerank(
        self, query: str, chunk_embeddings: list[ChunkEmbedding]
    ) -> list[ChunkEmbedding]:
        query = query.strip()

        if not query:
            raise unprocessable_content_error(
                message="No query provided for reranking",
                error_code="QUERY_IS_REQUIRED",
            )

        if not chunk_embeddings:
            raise unprocessable_content_error(
                message="No chunks provided for reranking",
                error_code="CHUNKS_ARE_REQUIRED",
            )

        if self._model is None:
            self._model = CrossEncoder(
                model_name_or_path=self._config.model_name,
                max_length=self._config.max_length,
            )

            _logger.info(f"Cross-encoder model has been initialized")

        pairs = [[query, embedding.chunk_text] for embedding in chunk_embeddings]

        scores = self._model.predict(
            pairs,
            batch_size=self._config.batch_size,
            show_progress_bar=False,
        )

        ranked = sorted(
            zip(chunk_embeddings, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )

        return [chunk for chunk, _ in ranked]
