"""
Base interface for a vector store operations.
"""

from abc import ABC, abstractmethod
from typing import Sequence, Dict, Optional, Any, List, Tuple

from src.logger.base_logger import BaseLogger

logger = BaseLogger(__name__)

# TODO ADD A WAY TO DELETE INDIVIDUAL VECTORS (OR VECTORS RELATED TO A DOCUMENT)


class VectorStore(ABC):
    """Defines the methods a vector store should implement."""

    # ========================== INDEX METHODS ==========================

    @abstractmethod
    def create_vector_index(self, index_id: Optional[str] = None) -> str:
        """
        Create an empty index and return its ID.
        """
        raise NotImplementedError

    @abstractmethod
    def get_vector_index(self, index_id: str) -> Optional[Any]:
        """
        Load and return the index object.
        """
        raise NotImplementedError

    @abstractmethod
    def get_vector_indexes(self, index_ids: Optional[List[str]]) -> List[Any]:
        """
        List all existing index IDs.
        :param index_ids:
        """
        raise NotImplementedError

    @abstractmethod
    def delete_vector_index(self, index_id: str) -> None:
        """
        Delete an index and all associated data.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_vector_indexes(self, index_ids: Optional[List[str]]) -> None:
        """
        Delete multiple indexes and all associated data.
        """
        raise NotImplementedError

    @abstractmethod
    def vector_index_exists(self, index_id: str) -> bool:
        """
        Check whether an index exists.
        """
        raise NotImplementedError

    @abstractmethod
    def get_vector_index_stats(self, index_id: str) -> Dict[str, Any]:
        """
        Return index statistics.
        """
        raise NotImplementedError

    # ========================== VECTOR METHODS ==========================

    @abstractmethod
    def add_vectors(
        self,
        index_id: str,
        vectors: Sequence,
        metadata: Sequence[dict],
    ) -> None:
        """
        Add vectors to an existing index.

        Args:
            index_id: The ID of the index to add vectors to.
            vectors: The sequence of vector embeddings to add.
            metadata: The sequence of metadata dictionaries corresponding to
                each vector.
        """
        raise NotImplementedError

    @abstractmethod
    def load_vectors(
        self,
        index_id: str,
    ) -> Tuple[Any, List[dict]]:
        """
        Load index and metadata from an existing index.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_vectors(
        self,
        index_id: str,
    ) -> None:
        """
        Delete vectors from an existing index.
        """
        raise NotImplementedError
