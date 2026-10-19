from uuid import UUID

from pydantic import Field

from src.rag.services.chunk.chunker import ChunkerConfig, Chunker, Chunk
from src.rag.services.chunk.utils import merge_undersized_chunks


class RecursiveCharChunkerConfig(ChunkerConfig):
    separators: list[str] = Field(
        default_factory=lambda: [
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            " ",
            "",
        ]
    )


class RecursiveCharacterSplittingChunker(Chunker):

    def __init__(self, config: RecursiveCharChunkerConfig):
        self._config = config

    async def chunk(self, text: str, source_id: UUID) -> list[Chunk]:
        if not text or not text.strip():
            return []

        leaves = self._split_with_offsets(
            text=text, separators=self._config.separators, base_offset=0
        )

        merged_spans = self._merge_leaves(leaves, text)

        chunks = self._spans_to_chunks(merged_spans, text, source_id=source_id)

        return merge_undersized_chunks(
            chunks=chunks,
            text=text,
            min_chunk_size=self._config.min_chunk_size,
            length_function=self._config.length_function,
            chunk_size=self._config.chunk_size,
        )

    # ------------------------ Leaf Generation ------------------------

    def _split_with_offsets(
        self, text: str, separators: list[str], base_offset: int
    ) -> list[tuple[int, int]]:
        """
        Recursively split the text into leaves, returning a list of (start, end)
        offsets for each leaf. The base_offset is used to adjust the offsets
        to the original text's position.
        """
        if self._config.length_function(text) <= self._config.chunk_size:
            return [(base_offset, base_offset + len(text))]

        if not separators:
            return self._hard_split(text, base_offset)

        separator, remaining = separators[0], separators[1:]

        if separator == "":
            return self._hard_split(text, base_offset)

        parts = text.split(separator)

        leaves: list[tuple[int, int]] = []
        cursor = base_offset

        for i, part in enumerate(parts):
            leaves.extend(self._split_with_offsets(part, remaining, cursor))
            cursor += len(part)

            if i < len(parts) - 1:
                cursor += len(separator)

        return leaves

    def _hard_split(self, text: str, base_offset: int) -> list[tuple[int, int]]:
        leaves: list[tuple[int, int]] = []
        pos = 0

        while pos < len(text):
            end = self._find_max_fitting_end(text, pos)
            leaves.append((base_offset + pos, base_offset + end))
            pos = end

        return leaves

    def _find_max_fitting_end(self, text: str, pos: int) -> int:
        """
        Find the maximum end index for a chunk starting at pos that fits within
        the chunk_size limit. Uses binary search to find the largest end index
        such that the length of text[pos:end] is less than or equal to
        chunk_size.
        """
        low, high, best = pos + 1, len(text), pos + 1

        while low <= high:
            middle = (low + high) // 2
            if (
                self._config.length_function(text[pos:middle])
                <= self._config.chunk_size
            ):
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        return best

    # ------------------------ Leaf Merging ------------------------

    def _merge_leaves(
        self, leaves: list[tuple[int, int]], text: str
    ) -> list[tuple[int, int]]:
        """
        Merge leaves into larger chunks, ensuring that each chunk does not
        exceed chunk_size and respects chunk_overlap. Returns a list of
        (start, end) offsets for each chunk.
        """
        if not leaves:
            return []

        merged: list[tuple[int, int]] = []
        window: list[tuple[int, int]] = []

        for leaf in leaves:
            if window:
                candidate_len = self._config.length_function(
                    text[window[0][0] : leaf[1]]
                )
                if candidate_len > self._config.chunk_size:
                    merged.append((window[0][0], window[-1][1]))
                    window = self._trim_for_overlap(window, text)

                    # The overlap tail plus this leaf can still be too big.
                    # Keep dropping from the front, same as trimming, until
                    # there is room, or the window is empty.
                    while (
                        window
                        and self._config.length_function(text[window[0][0] : leaf[1]])
                        > self._config.chunk_size
                    ):
                        window = window[1:]

            window.append(leaf)

        if window:
            merged.append((window[0][0], window[-1][1]))

        return merged

    def _trim_for_overlap(
        self, window: list[tuple[int, int]], text: str
    ) -> list[tuple[int, int]]:
        """
        Trim the window of leaves to ensure that the overlap does not exceed
        chunk_overlap. Returns the trimmed window.
        """
        if self._config.chunk_overlap <= 0:
            return []

        while (
            len(window) > 1
            and self._config.length_function(text[window[0][0] : window[-1][1]])
            > self._config.chunk_overlap
        ):
            window = window[1:]

        return window

    # ------------------------ Chunk Creation ------------------------

    @staticmethod
    def _spans_to_chunks(
        spans: list[tuple[int, int]], text: str, *, source_id: UUID
    ) -> list[Chunk]:
        """
        Convert a list of (start, end) spans into Chunk objects.
        """
        chunks: list[Chunk] = []

        for start, end in spans:
            chunk_text = text[start:end]

            if not chunk_text.strip():
                continue

            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=len(chunks),
                    source=source_id,
                    start_offset=start,
                    end_offset=end,
                    metadata={},
                )
            )

        return chunks
