import asyncio
import logging
import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sentence_transformers import CrossEncoder

from src.exceptions import server_error, unprocessable_content_error
from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.services.rerank.reranker import Reranker

_logger = logging.getLogger(__name__)


class CrossEncoderRerankerConfig(BaseModel):
    """
    Configuration for the CrossEncoderReranker.
    """

    model_config = ConfigDict(frozen=True)

    model_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    # Query and chunk are cut to this many tokens together.
    max_length: int = Field(gt=0)
    batch_size: int = Field(default=32, gt=0)


def _sort_key(score: object) -> float:
    """Sort NaN scores last, because NaN breaks the ordering of a sort."""
    value = float(score)
    return float("-inf") if math.isnan(value) else value


class CrossEncoderReranker(Reranker):
    """
    A reranker that uses a cross-encoder model to re-rank the retrieved chunks.

    Create one instance for the whole application. Each instance loads its
    own copy of the model.
    """

    def __init__(self, config: CrossEncoderRerankerConfig) -> None:
        self._config = config
        self._model: CrossEncoder | None = None
        self._lock = asyncio.Lock()

    async def warm_up(self) -> None:
        """Load the model now, so the first request does not wait for it."""
        async with self._lock:
            await self._ensure_model()

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
            return []

        pairs = [[query, embedding.chunk_text] for embedding in chunk_embeddings]

        async with self._lock:
            model = await self._ensure_model()

            try:
                scores = await asyncio.to_thread(
                    model.predict,
                    pairs,
                    batch_size=self._config.batch_size,
                    show_progress_bar=False,
                )
            except Exception as exc:
                _logger.exception("Reranking failed for %d chunks.", len(pairs))
                raise server_error(
                    message="The chunks could not be reranked.",
                    error_code="RERANK_ERROR",
                    cause=exc,
                ) from exc

        ranked = sorted(
            zip(chunk_embeddings, scores, strict=True),
            key=lambda item: _sort_key(item[1]),
            reverse=True,
        )

        return [chunk for chunk, _ in ranked]

    async def _ensure_model(self) -> CrossEncoder:
        """
        Load the model once. The caller must hold the lock.
        """
        if self._model is not None:
            return self._model

        try:
            model = await asyncio.to_thread(
                CrossEncoder,
                model_name_or_path=self._config.model_name,
                max_length=self._config.max_length,
            )

            _logger.info("Cross-encoder model %s loaded.", self._config.model_name)

            self._model = model

            return model
        except Exception as exc:
            _logger.exception(
                "Cross-encoder model %s failed to load.", self._config.model_name
            )
            raise server_error(
                message="The reranking model could not be loaded.",
                error_code="RERANKER_LOAD_ERROR",
                cause=exc,
            ) from exc
