"""
Unit tests for SentenceBasedChunker.
"""

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.rag.services.chunk.sentence_based import (
    SentenceBasedChunker,
    SentenceChunkerConfig,
)
from src.rag.services.extract.extractors.extractor import Segment

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def source_id():
    return uuid4()


def make_config(**overrides) -> SentenceChunkerConfig:
    defaults = {"chunk_size": 100, "chunk_overlap": 0, "min_chunk_size": 0}
    defaults.update(overrides)
    return SentenceChunkerConfig(**defaults)


def make_chunker(**overrides) -> SentenceBasedChunker:
    return SentenceBasedChunker(make_config(**overrides))


def offsets(chunks) -> list[tuple[int, int, str]]:
    return [(c.start_offset, c.end_offset, c.text) for c in chunks]


# Text used across most tests. Sentence boundaries, hand-verified:
#   "One."   -> start 0,  end 4
#   "Two."   -> start 5,  end 9
#   "Three." -> start 10, end 16
THREE_SENTENCES = "One. Two. Three."

# Text used for the max_sentences_per_chunk grouping test. Boundaries:
#   "One."   -> 0, 4      "Two."  -> 5, 9
#   "Three." -> 10, 16    "Four." -> 17, 22
FOUR_SENTENCES = "One. Two. Three. Four."

# Text used for the partial-overlap test, with word-count length_function.
# Sentence boundaries: "One two." -> 0,8   "Three four." -> 9,20
#                       "Five six." -> 21,30   "Seven eight." -> 31,43
WORD_COUNT_TEXT = "One two. Three four. Five six. Seven eight."


def word_count(s: str) -> int:
    return len(s.split())


# ---------------------------------------------------------------------------
# Core grouping: chunk_size and max_sentences_per_chunk
# ---------------------------------------------------------------------------


class TestCoreGrouping:

    @pytest.mark.asyncio
    async def test_all_sentences_fit_in_one_chunk_when_chunk_size_is_large(
        self, source_id
    ):
        chunker = make_chunker(chunk_size=1000)

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [(0, 16, "One. Two. Three.")]

    @pytest.mark.asyncio
    async def test_every_sentence_becomes_its_own_chunk_when_chunk_size_is_tiny(
        self, source_id
    ):
        chunker = make_chunker(chunk_size=1)

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [
            (0, 4, "One."),
            (5, 9, "Two."),
            (10, 16, "Three."),
        ]

    @pytest.mark.asyncio
    async def test_max_sentences_per_chunk_groups_by_count_regardless_of_size(
        self, source_id
    ):
        chunker = make_chunker(chunk_size=1000, max_sentences_per_chunk=2)

        chunks = await chunker.chunk(FOUR_SENTENCES, source_id)

        assert offsets(chunks) == [
            (0, 9, "One. Two."),
            (10, 22, "Three. Four."),
        ]
        assert [c.index for c in chunks] == [0, 1]
        assert all(c.source == source_id for c in chunks)

    @pytest.mark.asyncio
    async def test_max_sentences_per_chunk_one_isolates_each_sentence(self, source_id):
        chunker = make_chunker(chunk_size=1000, max_sentences_per_chunk=1)

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [
            (0, 4, "One."),
            (5, 9, "Two."),
            (10, 16, "Three."),
        ]

    @pytest.mark.asyncio
    async def test_single_oversized_sentence_is_kept_whole(self, source_id):
        # A sentence with no internal punctuation for the sentencizer to
        # split on is treated as one sentence, and a lone sentence is
        # never split further even when it alone exceeds chunk_size.
        text = "a" * 50
        chunker = make_chunker(chunk_size=5)

        chunks = await chunker.chunk(text, source_id)

        assert offsets(chunks) == [(0, 50, text)]


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
# min_chunk_size, wired through the shared merge_undersized_chunks helper
# ---------------------------------------------------------------------------


class TestMinChunkSize:

    @pytest.mark.asyncio
    async def test_small_chunks_all_merge_into_one_via_shared_utility(self, source_id):
        # max_sentences_per_chunk=1 first forces three tiny one-sentence
        # chunks, exactly like the grouping test above; min_chunk_size
        # set well above any of their individual sizes then forces the
        # shared merge_undersized_chunks helper to cascade them all back
        # into a single chunk identical to the "one big chunk" case.
        chunker = make_chunker(
            chunk_size=1000, max_sentences_per_chunk=1, min_chunk_size=999
        )

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [(0, 16, "One. Two. Three.")]


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


class TestOverlap:

    @pytest.mark.asyncio
    async def test_single_chunk_result_ignores_configured_overlap(self, source_id):
        # With only one chunk in the whole result, there is nothing for
        # it to overlap with, so a configured, positive chunk_overlap
        # has no effect at all.
        chunker = make_chunker(chunk_size=1000, chunk_overlap=5)

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [(0, 16, "One. Two. Three.")]

    @pytest.mark.asyncio
    async def test_overlap_pulls_the_entire_previous_chunk_when_it_has_one_sentence(
        self, source_id
    ):
        # Each previous chunk here contains exactly one sentence (from
        # max_sentences_per_chunk=1), so there is nothing finer than the
        # whole previous chunk available to pull in as overlap.
        chunker = make_chunker(
            chunk_size=1000, max_sentences_per_chunk=1, chunk_overlap=3
        )

        chunks = await chunker.chunk(THREE_SENTENCES, source_id)

        assert offsets(chunks) == [
            (0, 4, "One."),
            (0, 9, "One. Two."),
            (5, 16, "Two. Three."),
        ]

    @pytest.mark.asyncio
    async def test_overlap_pulls_only_the_last_sentence_when_that_satisfies_the_requirement(
        self, source_id
    ):
        # Each chunk here has two sentences, so the overlap loop has a
        # real choice to make. chunk_overlap=3 (word count) is enough
        # for the previous chunk's last sentence (2 words) alone, but
        # adding its first sentence too (2 more words = 4) would exceed
        # it, so only the last sentence should be pulled in.
        baseline = make_chunker(
            chunk_size=4, chunk_overlap=0, length_function=word_count
        )
        overlapping = make_chunker(
            chunk_size=4, chunk_overlap=3, length_function=word_count
        )

        baseline_chunks = await baseline.chunk(WORD_COUNT_TEXT, source_id)
        overlapping_chunks = await overlapping.chunk(WORD_COUNT_TEXT, source_id)

        assert offsets(baseline_chunks) == [
            (0, 20, "One two. Three four."),
            (21, 43, "Five six. Seven eight."),
        ]
        assert offsets(overlapping_chunks) == [
            (0, 20, "One two. Three four."),
            (9, 43, "Three four. Five six. Seven eight."),
        ]


# ---------------------------------------------------------------------------
# Tokenization is offloaded to a thread
# ---------------------------------------------------------------------------


class TestAsyncTokenization:

    @pytest.mark.asyncio
    async def test_tokenization_is_offloaded_to_a_thread(self, source_id):
        chunker = make_chunker(chunk_size=1000)

        with patch(
            "src.rag.services.chunk.sentence_based.asyncio.to_thread",
            wraps=asyncio.to_thread,
        ) as mock_to_thread:
            chunks = await chunker.chunk("One. Two.", source_id)

        assert mock_to_thread.call_count >= 1
        first_call_target = mock_to_thread.call_args_list[0].args[0]
        assert first_call_target is chunker._nlp
        assert offsets(chunks) == [(0, 9, "One. Two.")]


# ---------------------------------------------------------------------------
# chunk_stream (inherited from the Chunker base class)
# ---------------------------------------------------------------------------


class TestChunkStream:

    @pytest.mark.asyncio
    async def test_chunk_stream_joins_segments_and_sets_page_and_offsets(
        self, source_id
    ):
        # The second segment uses separator="" so the joined text is
        # "One. Two." with no blank line between the sentences.
        chunker = make_chunker(chunk_size=1000)

        async def segments():
            yield Segment(text="One. ", page=1)
            yield Segment(text="Two.", page=2, separator="")

        results = [c async for c in chunker.chunk_stream(segments(), source_id)]

        assert len(results) == 1
        assert offsets(results) == [(0, 9, "One. Two.")]
        assert results[0].index == 0
        assert results[0].metadata["page"] == 1


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:

    def test_max_sentences_per_chunk_defaults_to_none(self):
        config = SentenceChunkerConfig(chunk_size=10, chunk_overlap=0)

        assert config.max_sentences_per_chunk is None

    def test_max_sentences_per_chunk_rejects_non_positive_values(self):
        with pytest.raises(ValidationError):
            SentenceChunkerConfig(
                chunk_size=10, chunk_overlap=0, max_sentences_per_chunk=0
            )
