from src.rag.models.chunk_embedding import ChunkEmbedding
from src.rag.services.rerank.reranker import Reranker


class PassthroughReranker(Reranker):
    """
    A reranker that keeps the chunks in their retrieval (similarity) order.
    Used when RERANKER_ENABLED is false, so the cross-encoder model and torch
    are never loaded.
    """

    async def rerank(
        self, query: str, chunk_embeddings: list[ChunkEmbedding]
    ) -> list[ChunkEmbedding]:
        return list(chunk_embeddings)
