"""
Unit tests for the VectorStore implementations (FaissVectorStore).
Tests core functionality and edge cases.
"""

import pytest

from src.errors.api_exceptions import ApiException


# ==================== INDEX CREATION ====================


def test_create_vector_index_success(vector_store):
    """Test successful creation of a new vector index."""
    index_id = vector_store.create_vector_index()

    assert index_id is not None
    assert vector_store.vector_index_exists(index_id)


def test_create_vector_index_with_custom_id(vector_store):
    """Test creating a vector index with a custom ID."""
    custom_id = "custom_index_123"
    index_id = vector_store.create_vector_index(index_id=custom_id)

    assert index_id == custom_id
    assert vector_store.vector_index_exists(custom_id)


def test_create_vector_index_already_exists(vector_store, sample_index_id):
    """Test that creating a duplicate index raises an error."""
    with pytest.raises(ApiException) as exc_info:
        vector_store.create_vector_index(index_id=sample_index_id)

    assert exc_info.value.error.code == "INDEX_ALREADY_EXISTS"


# ==================== INDEX RETRIEVAL ====================


def test_get_vector_index_success(vector_store, sample_index_id):
    """Test retrieving an existing vector index."""
    index = vector_store.get_vector_index(sample_index_id)

    assert index is not None
    assert hasattr(index, "ntotal")  # FAISS index property


def test_get_vector_index_not_found(vector_store):
    """Test retrieving a non-existent index raises error."""
    with pytest.raises(ApiException) as exc_info:
        vector_store.get_vector_index("non_existent_index")

    assert exc_info.value.error.code == "INDEX_NOT_FOUND"


def test_get_vector_indexes_all(vector_store, multiple_indexes):
    """Test retrieving all vector indexes."""
    indexes = vector_store.get_vector_indexes(index_ids=None)

    assert len(indexes) >= len(multiple_indexes)


def test_get_vector_indexes_specific(vector_store, multiple_indexes):
    """Test retrieving specific vector indexes."""
    indexes = vector_store.get_vector_indexes(index_ids=multiple_indexes[:2])

    assert len(indexes) == 2


# ==================== INDEX DELETION ====================


def test_delete_vector_index_success(vector_store, sample_index_id):
    """Test successful deletion of a vector index."""
    vector_store.delete_vector_index(sample_index_id)

    assert not vector_store.vector_index_exists(sample_index_id)


def test_delete_vector_index_not_found(vector_store):
    """Test deleting a non-existent index raises error."""
    with pytest.raises(ApiException) as exc_info:
        vector_store.delete_vector_index("non_existent_index")

    assert exc_info.value.error.code == "INDEX_NOT_FOUND"


# ==================== VECTOR OPERATIONS ====================


def test_add_vectors_success(
    vector_store, sample_index_id, sample_vectors, sample_metadata
):
    """Test successfully adding vectors to an index."""
    vector_store.add_vectors(sample_index_id, sample_vectors, sample_metadata)

    stats = vector_store.get_vector_index_stats(sample_index_id)
    assert stats["total_vectors"] == len(sample_vectors)
    assert stats["dimension"] == len(sample_vectors[0])


def test_add_vectors_dimension_mismatch(vector_store, sample_index_id):
    """Test adding vectors with mismatched dimensions raises error."""
    # Add initial vectors
    initial_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    initial_metadata = [{"id": "1"}, {"id": "2"}]
    vector_store.add_vectors(sample_index_id, initial_vectors, initial_metadata)

    # Try to add vectors with different dimension
    mismatched_vectors = [[0.1, 0.2]]  # 2D instead of 3D
    mismatched_metadata = [{"id": "3"}]

    with pytest.raises(ApiException) as exc_info:
        vector_store.add_vectors(
            sample_index_id, mismatched_vectors, mismatched_metadata
        )

    assert exc_info.value.error.code == "VECTOR_DIMENSION_MISMATCH"


def test_add_vectors_metadata_size_mismatch(vector_store, sample_index_id):
    """Test adding vectors with mismatched metadata size raises error."""
    vectors = [[0.1, 0.2], [0.3, 0.4]]
    metadata = [{"id": "1"}]  # Only 1 metadata for 2 vectors

    with pytest.raises(ApiException) as exc_info:
        vector_store.add_vectors(sample_index_id, vectors, metadata)

    assert exc_info.value.error.code == "VECTORS_METADATA_SIZE_MISMATCH"


def test_load_vectors_success(
    vector_store, sample_index_id, sample_vectors, sample_metadata
):
    """Test loading vectors and metadata from an index."""
    vector_store.add_vectors(sample_index_id, sample_vectors, sample_metadata)

    index, metadata = vector_store.load_vectors(sample_index_id)

    assert index.ntotal == len(sample_vectors)
    assert len(metadata) == len(sample_metadata)


def test_delete_vectors_success(
    vector_store, sample_index_id, sample_vectors, sample_metadata
):
    """Test deleting all vectors from an index."""
    # Add vectors first
    vector_store.add_vectors(sample_index_id, sample_vectors, sample_metadata)

    # Delete all vectors
    vector_store.delete_vectors(sample_index_id)

    # Verify index is empty
    stats = vector_store.get_vector_index_stats(sample_index_id)
    assert stats["total_vectors"] == 0
    assert stats["metadata_entries"] == 0


# ==================== INDEX STATISTICS ====================


def test_get_vector_index_stats_empty(vector_store, sample_index_id):
    """Test getting stats for an empty index."""
    stats = vector_store.get_vector_index_stats(sample_index_id)

    assert stats["index_id"] == sample_index_id
    assert stats["total_vectors"] == 0
    assert stats["dimension"] is None
    assert stats["metadata_entries"] == 0


def test_get_vector_index_stats_with_vectors(
    vector_store, sample_index_id, sample_vectors, sample_metadata
):
    """Test getting stats for an index with vectors."""
    vector_store.add_vectors(sample_index_id, sample_vectors, sample_metadata)

    stats = vector_store.get_vector_index_stats(sample_index_id)

    assert stats["index_id"] == sample_index_id
    assert stats["total_vectors"] == len(sample_vectors)
    assert stats["dimension"] == len(sample_vectors[0])
    assert stats["metadata_entries"] == len(sample_metadata)
