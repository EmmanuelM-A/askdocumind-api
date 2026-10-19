"""
Unit tests for merge_undersized_chunks (src/rag/services/chunk/utils.py).
"""

from uuid import uuid4

import pytest

from src.rag.services.chunk.chunker import Chunk
from src.rag.services.chunk.utils import merge_undersized_chunks

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def source_id():
    return uuid4()


def make_chunk(
    text: str, index: int, source_id, start: int, end: int, metadata=None
) -> Chunk:
    return Chunk(
        text=text,
        index=index,
        source=source_id,
        start_offset=start,
        end_offset=end,
        metadata=metadata if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# No-op paths
# ---------------------------------------------------------------------------


class TestNoOpPaths:

    def test_min_chunk_size_zero_returns_chunks_unchanged(self, source_id):
        chunks = [make_chunk("a", 0, source_id, 0, 1)]

        result = merge_undersized_chunks(
            chunks, "a", min_chunk_size=0, length_function=len
        )

        assert result == chunks

    def test_empty_chunks_list_returns_empty_list(self):
        result = merge_undersized_chunks([], "", min_chunk_size=10, length_function=len)

        assert result == []

    def test_single_chunk_returns_unchanged_regardless_of_size(self, source_id):
        # A lone chunk has nothing to merge into in either direction.
        chunks = [make_chunk("a", 0, source_id, 0, 1)]

        result = merge_undersized_chunks(
            chunks, "a", min_chunk_size=100, length_function=len
        )

        assert result == chunks

    def test_no_chunks_below_threshold_returns_all_unchanged(self, source_id):
        text = "aaaaaaaaaa" + "bbbbbbbbbb"
        chunks = [
            make_chunk("aaaaaaaaaa", 0, source_id, 0, 10),
            make_chunk("bbbbbbbbbb", 1, source_id, 10, 20),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len
        )

        assert result == chunks


# ---------------------------------------------------------------------------
# Trailing and leading merges
# ---------------------------------------------------------------------------


class TestMerging:

    def test_small_trailing_chunk_merges_into_previous(self, source_id):
        text = "aaaaaaaaaabb"
        chunks = [
            make_chunk("aaaaaaaaaa", 0, source_id, 0, 10),
            make_chunk("bb", 1, source_id, 10, 12),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=100
        )

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 12)
        assert result[0].text == text

    def test_small_leading_chunk_merges_into_next(self, source_id):
        # A small first chunk has no earlier chunk to merge into during the
        # forward pass, so the second pass folds it into the next chunk.
        text = "aaaaaaaaaaaa"
        chunks = [
            make_chunk("aa", 0, source_id, 0, 2),
            make_chunk("aaaaaaaaaa", 1, source_id, 2, 12),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=100
        )

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 12)
        assert result[0].text == text

    def test_chain_of_small_chunks_merges_into_one(self, source_id):
        # All three chunks sit below min_chunk_size, so they cascade into
        # the first chunk during the forward pass.
        text = "a" * 9
        chunks = [
            make_chunk("aaa", 0, source_id, 0, 3),
            make_chunk("aaa", 1, source_id, 3, 6),
            make_chunk("aaa", 2, source_id, 6, 9),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=100
        )

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 9)
        assert result[0].text == text

    def test_indices_are_sequential_after_merge(self, source_id):
        text = "a" * 15
        chunks = [
            make_chunk("aa", 0, source_id, 0, 2),
            make_chunk("aa", 1, source_id, 2, 4),
            make_chunk("a" * 11, 2, source_id, 4, 15),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=3, length_function=len, chunk_size=100
        )

        assert len(result) == 2
        assert [c.index for c in result] == list(range(len(result)))

    def test_merged_text_matches_text_slice_exactly(self, source_id):
        text = "hello world, this is a test"
        chunks = [
            make_chunk("hello world,", 0, source_id, 0, 12),
            make_chunk(" this", 1, source_id, 12, 17),
            make_chunk(" is a test", 2, source_id, 17, 27),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=6, length_function=len, chunk_size=100
        )

        assert len(result) == 2
        for c in result:
            assert text[c.start_offset : c.end_offset] == c.text

    def test_metadata_of_surviving_chunk_is_preserved(self, source_id):
        text = "aaaaaaaaaabb"
        chunks = [
            make_chunk(
                "aaaaaaaaaa", 0, source_id, 0, 10, metadata={"node_type": "function"}
            ),
            make_chunk("bb", 1, source_id, 10, 12, metadata={"node_type": "preamble"}),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=100
        )

        assert len(result) == 1
        # The surviving chunk keeps its own metadata. Merging only touches
        # text and offsets.
        assert result[0].metadata == {"node_type": "function"}


# ---------------------------------------------------------------------------
# chunk_size cap
# ---------------------------------------------------------------------------


class TestChunkSizeCap:

    def test_merge_blocked_when_combined_would_exceed_chunk_size(self, source_id):
        text = "a" * 10
        chunks = [
            make_chunk("a" * 8, 0, source_id, 0, 8),
            make_chunk("aa", 1, source_id, 8, 10),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=9
        )

        assert len(result) == 2
        assert (result[0].start_offset, result[0].end_offset) == (0, 8)
        assert (result[1].start_offset, result[1].end_offset) == (8, 10)

    def test_chunk_size_none_allows_merge_regardless_of_size(self, source_id):
        # With no chunk_size ceiling, as a syntax-aware chunker uses.
        text = "a" * 30
        chunks = [
            make_chunk("a" * 20, 0, source_id, 0, 20),
            make_chunk("a" * 3, 1, source_id, 20, 23),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=None
        )

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 23)

    def test_leading_merge_blocked_by_chunk_size_leaves_small_chunk_in_output(
        self, source_id
    ):
        # The leading-chunk fold runs once after the forward pass. If
        # chunk_size blocks this single attempt, the small leading chunk
        # stays in the output.
        text = "aabbcccccc"
        chunks = [
            make_chunk("aa", 0, source_id, 0, 2),
            make_chunk("bb", 1, source_id, 2, 4),
            make_chunk("cccccc", 2, source_id, 4, 10),
        ]

        result = merge_undersized_chunks(
            chunks, text, min_chunk_size=5, length_function=len, chunk_size=6
        )

        # "aa" and "bb" merge during the forward pass into a 4 character
        # chunk, still below min_chunk_size=5. The leading fold then tries
        # to join this chunk with "cccccc", but the combined length of 10
        # exceeds chunk_size=6, so the small chunk stays.
        assert len(result) == 2
        assert result[0].text == "aabb"
        assert (result[0].start_offset, result[0].end_offset) == (0, 4)
        assert result[1].text == "cccccc"
        assert [c.index for c in result] == [0, 1]


# ---------------------------------------------------------------------------
# Custom length_function
# ---------------------------------------------------------------------------


class TestCustomLengthFunction:

    def test_custom_length_function_is_used_for_size_check(self, source_id):
        # A word count length function merges on word count, not
        # character count.
        text = "one two three four five"
        chunks = [
            make_chunk("one two", 0, source_id, 0, 7),
            make_chunk(" three", 1, source_id, 7, 13),
            make_chunk(" four five", 2, source_id, 13, 23),
        ]

        result = merge_undersized_chunks(
            chunks,
            text,
            min_chunk_size=2,
            length_function=lambda s: len(s.split()),
            chunk_size=100,
        )

        # " three" has one word, below the 2 word threshold, so it merges
        # into "one two" and leaves two final chunks.
        assert len(result) == 2
        assert result[0].text == "one two three"
        assert result[1].text == " four five"
