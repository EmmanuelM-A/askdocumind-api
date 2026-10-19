"""
Unit tests for RecursiveCharacterSplittingChunker.
"""

from uuid import uuid4

import pytest

from src.rag.services.chunk.recursive_character_splitter import (
    RecursiveCharacterSplittingChunker,
    RecursiveCharChunkerConfig,
)
from src.rag.services.extract.extractors.extractor import Segment

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def source_id():
    return uuid4()


def make_config(**overrides) -> RecursiveCharChunkerConfig:
    defaults = dict(chunk_size=10, chunk_overlap=0, min_chunk_size=0)
    defaults.update(overrides)
    return RecursiveCharChunkerConfig(**defaults)


def make_chunker(**overrides) -> RecursiveCharacterSplittingChunker:
    return RecursiveCharacterSplittingChunker(make_config(**overrides))


# ---------------------------------------------------------------------------
# Core recursive splitting, via chunk()
# ---------------------------------------------------------------------------


class TestChunkCore:

    @pytest.mark.asyncio
    async def test_paragraph_separator_produces_two_correctly_offset_chunks(
        self, source_id
    ):
        # "\n\n" is the first separator tried and splits this text into two
        # ten-character pieces that each already fit chunk_size, so no
        # further recursion or merging happens.
        text = "AAAAAAAAAA\n\nBBBBBBBBBB"
        chunker = make_chunker(chunk_size=10)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 2
        assert (chunks[0].start_offset, chunks[0].end_offset) == (0, 10)
        assert chunks[0].text == "AAAAAAAAAA"
        assert (chunks[1].start_offset, chunks[1].end_offset) == (12, 22)
        assert chunks[1].text == "BBBBBBBBBB"

        # The two-character "\n\n" separator (offsets 10-12) is dropped from
        # both chunks rather than swallowed into either one.
        assert [c.index for c in chunks] == [0, 1]
        assert all(c.source == source_id for c in chunks)
        assert all(text[c.start_offset : c.end_offset] == c.text for c in chunks)

    @pytest.mark.asyncio
    async def test_recursion_falls_through_separator_levels_to_sentence_boundary(
        self, source_id
    ):
        # No "\n\n" or "\n" anywhere in this text, so splitting recurses
        # past both before ". " produces fitting pieces.
        text = "AAAAAAAAAA. BBBBBBBBBB. CCCCCCCCCC"
        chunker = make_chunker(chunk_size=10)

        chunks = await chunker.chunk(text, source_id)

        assert [c.text for c in chunks] == [
            "AAAAAAAAAA",
            "BBBBBBBBBB",
            "CCCCCCCCCC",
        ]
        assert [(c.start_offset, c.end_offset) for c in chunks] == [
            (0, 10),
            (12, 22),
            (24, 34),
        ]


# ---------------------------------------------------------------------------
# Hard-split fallback (the empty-separator crash fix)
# ---------------------------------------------------------------------------


class TestHardSplitFallback:

    @pytest.mark.asyncio
    async def test_text_with_no_separators_does_not_crash(self, source_id):
        # No spaces, newlines, or punctuation anywhere, so every separator
        # in the default list fails to match and splitting falls through to
        # the "" sentinel. The text hard-splits at chunk_size.
        text = "a" * 25
        chunker = make_chunker(chunk_size=10)

        chunks = await chunker.chunk(text, source_id)

        assert [(c.start_offset, c.end_offset) for c in chunks] == [
            (0, 10),
            (10, 20),
            (20, 25),
        ]
        assert [c.text for c in chunks] == ["a" * 10, "a" * 10, "a" * 5]

    def test_hard_split_with_custom_length_function_uses_binary_search(self):
        # length_function is not len, so a correct hard split must not cut
        # every chunk_size raw characters. It binary searches for the
        # largest slice whose length_function value fits.
        chunker = make_chunker(chunk_size=5, length_function=lambda s: len(s) // 2)

        result = chunker._hard_split("a" * 12, 0)

        assert result == [(0, 11), (11, 12)]

    @pytest.mark.asyncio
    async def test_hard_split_leaves_receive_no_additional_overlap(self, source_id):
        # Hard-split pieces land exactly at chunk_size with no finer
        # sub-leaves to trim between, so a configured overlap cannot
        # produce overlapping chunks here. The overflow guard in
        # _merge_leaves drops the whole overlap tail instead of producing
        # an oversized chunk.
        text = "a" * 20
        chunker = make_chunker(chunk_size=10, chunk_overlap=5)

        chunks = await chunker.chunk(text, source_id)

        assert [(c.start_offset, c.end_offset) for c in chunks] == [
            (0, 10),
            (10, 20),
        ]


# ---------------------------------------------------------------------------
# _merge_leaves: overlap trimming and the chunk_size overflow fix
# ---------------------------------------------------------------------------


class TestMergeLeaves:

    def test_overlap_trim_still_respects_chunk_size_after_drop(self):
        # Trimming the window to its overlap tail leaves one leaf, because
        # the trim loop never drops the last leaf. Adding the new leaf then
        # pushes the span past chunk_size, so the overflow guard drops the
        # tail and sacrifices the overlap.
        chunker = make_chunker(chunk_size=10, chunk_overlap=5)
        text = "a" * 18
        leaves = [(0, 5), (5, 10), (10, 18)]

        result = chunker._merge_leaves(leaves, text)

        assert result == [(0, 10), (10, 18)]

    def test_normal_multi_leaf_overlap_trimming(self):
        # The kept tail leaf is 4 characters, which exceeds chunk_overlap=3.
        # The trim loop keeps the last leaf, so overlap is built from whole
        # leaves and can exceed chunk_overlap.
        chunker = make_chunker(chunk_size=10, chunk_overlap=3)
        text = "a" * 16
        leaves = [(0, 4), (4, 8), (8, 12), (12, 16)]

        result = chunker._merge_leaves(leaves, text)

        assert result == [(0, 8), (4, 12), (8, 16)]


class TestRealOverlapEndToEnd:

    @pytest.mark.asyncio
    async def test_overlap_produces_genuinely_overlapping_chunks_with_fine_leaves(
        self, source_id
    ):
        # Unlike the hard-split case above, "\n" splitting produces several
        # small leaves, giving _merge_leaves room to trim for overlap.
        text = "aa\nbb\ncc\ndd\nee"
        chunker = make_chunker(chunk_size=10, chunk_overlap=3, separators=["\n"])

        chunks = await chunker.chunk(text, source_id)

        assert [(c.start_offset, c.end_offset, c.text) for c in chunks] == [
            (0, 8, "aa\nbb\ncc"),
            (6, 14, "cc\ndd\nee"),
        ]


# ---------------------------------------------------------------------------
# _trim_for_overlap
# ---------------------------------------------------------------------------


class TestTrimForOverlap:

    def test_overlap_zero_returns_empty_window(self):
        chunker = make_chunker(chunk_size=10, chunk_overlap=0)

        result = chunker._trim_for_overlap([(0, 3), (3, 6)], "a" * 6)

        assert result == []

    def test_trims_down_to_narrowest_window_within_reach(self):
        chunker = make_chunker(chunk_size=10, chunk_overlap=4)

        result = chunker._trim_for_overlap([(0, 3), (3, 6), (6, 9)], "a" * 9)

        assert result == [(6, 9)]


# ---------------------------------------------------------------------------
# _spans_to_chunks
# ---------------------------------------------------------------------------


class TestSpansToChunks:

    def test_blank_spans_are_filtered_and_indices_stay_sequential(self, source_id):
        text = "aaaaa   bbbbb"
        spans = [(0, 5), (5, 8), (8, 13)]
        chunker = make_chunker()

        chunks = chunker._spans_to_chunks(spans, text, source_id=source_id)

        assert [c.text for c in chunks] == ["aaaaa", "bbbbb"]
        assert [c.index for c in chunks] == [0, 1]
        assert [(c.start_offset, c.end_offset) for c in chunks] == [(0, 5), (8, 13)]


# ---------------------------------------------------------------------------
# Empty / degenerate input
# ---------------------------------------------------------------------------


class TestEmptyInput:

    @pytest.mark.asyncio
    async def test_empty_string_returns_no_chunks(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk("", source_id)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_no_chunks(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk("   \n\t  \n", source_id)
        assert chunks == []


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestConfigDefaults:

    def test_default_separators_order(self):
        config = RecursiveCharChunkerConfig(chunk_size=100, chunk_overlap=0)

        assert config.separators == ["\n\n", "\n", ". ", "! ", "? ", " ", ""]


# ---------------------------------------------------------------------------
# chunk_stream (inherited from the Chunker base class)
# ---------------------------------------------------------------------------


class TestChunkStream:

    @pytest.mark.asyncio
    async def test_chunk_stream_joins_segments_with_separator_and_sets_page(
        self, source_id
    ):
        # The default Segment separator is "\n\n", so the joined text is
        # "Hello\n\nworld" (12 characters). The text fits in one chunk, so
        # the final flush yields a single chunk with stream-wide offsets.
        # The chunk starts in the first segment, so it gets that page.
        chunker = make_chunker(chunk_size=100)

        async def segments():
            yield Segment(text="Hello", page=1)
            yield Segment(text="world", page=2)

        results = [c async for c in chunker.chunk_stream(segments(), source_id)]

        assert len(results) == 1
        assert results[0].text == "Hello\n\nworld"
        assert (results[0].start_offset, results[0].end_offset) == (0, 12)
        assert results[0].index == 0
        assert results[0].metadata["page"] == 1
