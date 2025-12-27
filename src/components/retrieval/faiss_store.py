"""
Handles vector store operations for retrieval-augmented generation (RAG)
systems.
"""

import os
import pickle
import uuid
from abc import ABC
from typing import Sequence, Dict, Optional, Any, List, Tuple
import numpy as np
import faiss


from src.config.configs import settings
from src.errors.custom_exceptions import (
    throw_unprocessable_entity_error,
    throw_not_found_error,
    throw_server_error,
)
from src.logger.base_logger import BaseLogger
from src.components.retrieval.vector_store import VectorStore
from src.utils.helper import does_file_exist


class FaissVectorStore(VectorStore, ABC):
    """
    Concrete implementation of VectorStore using FAISS for vector storage.
    Only for local development and testing purposes.
    """

    def __init__(self):
        """Initialize the FAISS vector store."""

        self._logger = BaseLogger(__name__)

        self.index_dir = settings.vector.DEV_VECTOR_STORE
        self.metadata_dir = settings.vector.DEV_METADATA_STORE

        os.makedirs(self.index_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)

    # ========================== INDEX METHODS ==========================

    def create_vector_index(self, index_id: Optional[str] = None) -> str:
        if index_id is None:
            index_id = uuid.uuid4().hex

        if self.vector_index_exists(index_id):
            throw_unprocessable_entity_error(
                message=f"Index '{index_id}' already exists.",
                error_code="INDEX_ALREADY_EXISTS",
            )

        # Create an EMPTY index placeholder (dimension unknown for now)
        index = faiss.IndexFlatL2(1)
        index.reset()

        try:
            faiss.write_index(index, self._index_path(index_id))

            with open(self._metadata_path(index_id), "wb") as f:
                pickle.dump([], f)
        except (OSError, pickle.PickleError) as e:
            throw_server_error(
                message=f"Failed to create the index '{index_id}'",
                error_code="INDEX_CREATION_FAILED",
                stack_trace=str(e),
            )

        self._logger.info(f"Created empty FAISS index: {index_id}")

        return index_id

    def get_vector_index(self, index_id: str) -> Optional[faiss.Index]:
        index_path = self._index_path(index_id)

        if not does_file_exist(index_path):
            throw_not_found_error(
                message="Index not found.",
                error_code="INDEX_NOT_FOUND",
            )

        return self._safe_read_index(index_id)

    def get_vector_indexes(self, index_ids: Optional[List[str]]) -> List[faiss.Index]:
        if index_ids is None:
            indexes = [
                self.get_vector_index(index_id=file.replace(".faiss", ""))
                for file in os.listdir(self.index_dir)
                if file.endswith(".faiss")
            ]
        else:
            indexes = [self.get_vector_index(index_id) for index_id in index_ids]

        self._logger.info(
            f"Retrieved {len(indexes)} vector indexes from the vector store."
        )

        return indexes

    def delete_vector_index(self, index_id: str) -> None:
        if not self.vector_index_exists(index_id):
            throw_not_found_error(
                message=f"The index '{index_id}' not found.",
                error_code="INDEX_NOT_FOUND",
            )

        index_path = self._index_path(index_id)
        metadata_path = self._metadata_path(index_id)

        os.remove(index_path)
        os.remove(metadata_path)

        self._logger.info(f"Deleted index: {index_id}")

    def delete_vector_indexes(self, index_ids: Optional[List[str]]) -> None:
        if index_ids is None:
            index_ids = [
                self.delete_vector_index(file.replace(".faiss", ""))
                for file in os.listdir(self.index_dir)
                if file.endswith(".faiss")
            ]
        else:
            for index_id in index_ids:
                self.delete_vector_index(index_id)

        self._logger.info(f"Deleted {len(index_ids)} indexes.")

    def vector_index_exists(self, index_id: str) -> bool:
        return does_file_exist(self._index_path(index_id)) and does_file_exist(
            self._metadata_path(index_id)
        )

    def get_vector_index_stats(self, index_id: str) -> Dict[str, Any]:
        index, metadata = self.load_vectors(index_id)

        return {
            "index_id": index_id,
            "total_vectors": index.ntotal,
            "dimension": index.d if index.ntotal > 0 else None,
            "metadata_entries": len(metadata),
        }

    # ========================== VECTOR METHODS ==========================

    def add_vectors(
        self,
        index_id: str,
        vectors: Sequence,
        metadata: Sequence[dict],
    ) -> None:
        """
        Add vectors to an existing index.
        """

        if not self.vector_index_exists(index_id):
            throw_not_found_error(
                message="Index does not exist.",
                error_code="INDEX_NOT_FOUND",
            )

        if not vectors:
            throw_unprocessable_entity_error(
                message="No vectors provided.",
                error_code="NO_VECTORS",
            )

        if not metadata:
            throw_unprocessable_entity_error(
                message="No metadata provided.",
                error_code="NO_METADATA",
            )

        if len(vectors) != len(metadata):
            throw_unprocessable_entity_error(
                message="Vectors and metadata length mismatch.",
                error_code="VECTORS_METADATA_SIZE_MISMATCH",
            )

        # Load existing index + metadata FIRST
        index, existing_metadata = self.load_vectors(index_id)

        # Convert ONCE
        vectors_np = np.asarray(vectors, dtype="float32")
        num_vectors, dim = vectors_np.shape

        # Handle first insertion (index is empty placeholder)
        if index.ntotal == 0:
            if num_vectors > settings.vector.MAX_VECTORS_IN_MEMORY:
                self._logger.debug(f"Creating IVFFlat index for {num_vectors} vectors")
                nlist = min(int(np.sqrt(num_vectors)), 1000)
                quantizer = faiss.IndexFlatL2(dim)
                index = faiss.IndexIVFFlat(quantizer, dim, nlist)
                index.train(vectors_np)
            else:
                self._logger.debug(f"Creating FlatL2 index for {num_vectors} vectors")
                index = faiss.IndexFlatL2(dim)

        # Dimension check
        if index.d != dim:
            throw_unprocessable_entity_error(
                message="Vector dimension mismatch.",
                error_code="VECTOR_DIMENSION_MISMATCH",
            )

        # Add vectors in batches
        batch_size = settings.vector.VECTOR_BATCH_SIZE

        for start in range(0, num_vectors, batch_size):
            end = start + batch_size
            batch = vectors_np[start:end]
            index.add(batch)

        # Append metadata
        existing_metadata.extend(metadata)

        # Persist once
        self._persist(index_id, index, existing_metadata)

        # Explicit cleanup
        del vectors_np

        self._logger.debug(
            f"Added {num_vectors} vectors to index '{index_id}'. "
            f"Total vectors: {index.ntotal}"
        )

    def load_vectors(self, index_id: str) -> Tuple[faiss.Index, List[dict]]:
        if not self.vector_index_exists(index_id):
            throw_not_found_error(
                message=f"The index '{index_id}' does not exist.",
                error_code="INDEX_NOT_FOUND",
            )

        index = self._safe_read_index(index_id)

        with open(self._metadata_path(index_id), "rb") as f:
            metadata = pickle.load(f)

        return index, metadata

    def delete_vectors(
        self,
        index_id: str,
    ) -> None:
        if not self.vector_index_exists(index_id):
            throw_not_found_error(
                message=f"The index '{index_id}' does not exist.",
                error_code="INDEX_NOT_FOUND",
            )

        # Load index and metadata
        index, _ = self.load_vectors(index_id)

        # Remove all vectors
        index.reset()

        # Clear metadata
        empty_metadata: list[dict] = []

        # Persist cleared index + metadata
        self._persist(index_id, index, empty_metadata)

        self._logger.info(f"Cleared all vectors from index '{index_id}'.")

    # ========================== HELPER METHODS ==========================

    def _safe_read_index(self, index_id: str) -> Any | None:
        """
        Safely read a FAISS index from disk.

        Args:
            index_id: ID of the index to read.

        Returns:
            FAISS index object.

        Raises:
            ServerError: If reading the index fails.
        """

        try:
            index = faiss.read_index(self._index_path(index_id))
            return index
        except OSError as e:
            throw_server_error(
                message=f"Failed to read index '{index_id}'",
                error_code="READ_INDEX_FAILED",
                stack_trace=str(e),
            )
            return None

    def _persist(
        self,
        index_id: str,
        index: faiss.Index,
        metadata: List[dict],
    ) -> None:
        """
        Persist the FAISS index and metadata to disk.

        Args:
            index_id: ID of the index.
            index: FAISS index object to persist.
            metadata: List of metadata dictionaries to persist.

        Raises:
            ServerError: If persisting the index or metadata fails.
        """

        try:
            faiss.write_index(index, self._index_path(index_id))

            with open(self._metadata_path(index_id), "wb") as f:
                pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)
        except (OSError, pickle.PickleError) as e:
            throw_server_error(
                message=f"Failed to persist index '{index_id}'",
                error_code="PERSIST_INDEX_FAILED",
                stack_trace=str(e),
            )

    def _index_path(self, index_id: str) -> str:
        """
        Get the file path for the FAISS index.

        Args:
            index_id: ID of the index.

        Returns:
            File path for the FAISS index.
        """
        return os.path.join(self.index_dir, f"{index_id}.faiss")

    def _metadata_path(self, index_id: str) -> str:
        """
        Get the file path for the metadata pickle file.

        Args:
            index_id: ID of the index.

        Returns:
            File path for the metadata pickle file.
        """
        return os.path.join(self.metadata_dir, f"{index_id}.pkl")
