"""
Sentence-based chunker implementation using spaCy for sentence tokenization.
"""

import asyncio
from uuid import UUID

import spacy
from pydantic import Field
from spacy.language import Language

from src.rag.services.chunk.chunker import ChunkConfig, Chunker, Chunk
from src.rag.services.chunk.utils import merge_undersized_chunks


class SentenceChunkerConfig(ChunkConfig):
    max_sentences_per_chunk: int | None = Field(default=None, ge=1)


class SentenceBasedChunker(Chunker):
    """
    A chunker that splits text into chunks based on sentence boundaries.

    Note on chunk_overlap: unlike the other chunkers in this codebase,
    overlap here is applied by growing an already-built chunk backward
    with whole sentences pulled from the end of the previous chunk,
    rather than by a sliding window over fixed-size pieces. This keeps
    every overlap region aligned to a sentence boundary, but it also
    means chunk_size is a target for the chunk's own content, not a
    hard ceiling on the final chunk once overlap is added: a chunk can
    come out larger than chunk_size by roughly the configured
    chunk_overlap amount.
    """

    def __init__(self, config: SentenceChunkerConfig):
        self._config = config
        self._nlp = self._create_tokenizer()

    @staticmethod
    def _create_tokenizer() -> Language:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp

    async def chunk(
        self,
        text: str,
        source_id: UUID,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        doc = await asyncio.to_thread(self._nlp, text)
        sentences = list(doc.sents)

        if not sentences:
            return []

        chunks = self._build_chunks(
            sentences,
            text,
            source_id=source_id,
        )

        chunks = merge_undersized_chunks(
            chunks,
            text,
            min_chunk_size=self._config.min_chunk_size,
            length_function=self._config.length_function,
            chunk_size=self._config.chunk_size,
        )

        return await self._apply_overlap(chunks, text)

    def _build_chunks(
        self,
        sentences,
        text: str,
        source_id: UUID,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []

        current_start: int = 0
        current_end: int = 0
        current_sentence_count = 0

        for sentence in sentences:
            sentence_start = sentence.start_char
            sentence_end = sentence.end_char

            if current_start is None:
                current_start = sentence_start

            candidate_end = sentence_end
            candidate_text = text[current_start:candidate_end]

            exceeds_size = (
                self._config.length_function(candidate_text) > self._config.chunk_size
            )

            exceeds_sentence_limit = (
                self._config.max_sentences_per_chunk is not None
                and current_sentence_count >= self._config.max_sentences_per_chunk
            )

            if current_sentence_count > 0 and (exceeds_size or exceeds_sentence_limit):
                chunks.append(
                    Chunk(
                        text=text[current_start:current_end],
                        index=len(chunks),
                        source=source_id,
                        start_offset=current_start,
                        end_offset=current_end,
                    )
                )

                current_start = sentence_start
                current_sentence_count = 0

            current_end = sentence_end
            current_sentence_count += 1

        if current_start is not None and current_end is not None:
            chunks.append(
                Chunk(
                    text=text[current_start:current_end],
                    index=len(chunks),
                    source=source_id,
                    start_offset=current_start,
                    end_offset=current_end,
                )
            )

        return chunks

    async def _apply_overlap(
        self,
        chunks: list[Chunk],
        text: str,
    ) -> list[Chunk]:
        if self._config.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: list[Chunk] = []

        for index, chunk in enumerate(chunks):
            if index == 0:
                overlapped.append(chunk)
                continue

            previous = chunks[index - 1]

            """
            Re-tokenize the previous chunk to get sentence boundaries.
            This is necessary because we want to ensure that the overlap
            respects sentence boundaries, rather than cutting off in the middle
            of a sentence. We will walk backwards through the sentences
            of the previous chunk until we have accumulated enough characters
            to satisfy the chunk_overlap requirement. If we reach the beginning
            of the previous chunk without accumulating enough characters, we will
            simply use the entire previous chunk as the overlap.
            """
            previous_doc = await asyncio.to_thread(self._nlp, previous.text)
            previous_sentences = list(previous_doc.sents)

            if not previous_sentences:
                overlapped.append(chunk)
                continue

            overlap_length = 0
            overlap_start_relative: int | None = None

            for sentence in reversed(previous_sentences):
                sentence_length = self._config.length_function(sentence.text)

                if (
                    overlap_length > 0
                    and overlap_length + sentence_length > self._config.chunk_overlap
                ):
                    break

                overlap_length += sentence_length
                overlap_start_relative = sentence.start_char

            if overlap_start_relative is None:
                overlapped.append(chunk)
                continue

            overlap_start = previous.start_offset + overlap_start_relative

            new_start = min(
                overlap_start,
                chunk.start_offset,
            )

            new_end = chunk.end_offset

            overlapped.append(
                Chunk(
                    text=text[new_start:new_end],
                    index=index,
                    source=chunk.source,
                    start_offset=new_start,
                    end_offset=new_end,
                    metadata=chunk.metadata.copy(),
                )
            )

        return overlapped
