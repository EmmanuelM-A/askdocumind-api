from typing import overload

from src.database.dependencies import DbSession
from src.rag.services.store import StoreChunkEmbeddingService


def get_rag_storage_service() -> StoreChunkEmbeddingService:
    """
    Provide a StoreChunkEmbeddingService instance for the current request.
    """
    pass


def build_rag_storage_service(session: DbSession) -> StoreChunkEmbeddingService:
    """
    Provide a StoreChunkEmbeddingService instance for the current request.
    """
    pass
