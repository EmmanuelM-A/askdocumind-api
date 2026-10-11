"""
Shared helper functions used across chunker implementations.
"""

from typing import Callable

from src.rag.services.chunk.chunker import Chunk


def merge_undersized_chunks(
    chunks: list[Chunk],
    text: str,
    min_chunk_size: int,
    length_function: Callable[[str], int],
    chunk_size: int | None = None,
) -> list[Chunk]:
    """
    Fold any chunk below `min_chunk_size` into a neighboring chunk instead
    of leaving small fragments (a lone docstring, a short trailing
    sentence, a stray leading line) indexed on their own.

    Trailing small chunks merge into the one before them. A small first
    chunk, which has no earlier chunk to merge into during that pass,
    is folded forward into the one after it in a second pass.

    Merged text is always re-sliced from the original document rather
    than concatenated from cached chunk text, so a chunk's text always
    equals `text[start_offset:end_offset]` exactly.

    `chunk_size`, if given, blocks a merge whenever the combined span
    would exceed it, leaving both chunks separate instead of producing
    an oversized chunk. Pass `None` to merge regardless of the resulting
    size, appropriate for a chunker (such as a syntax-aware one) that
    does not enforce a hard `chunk_size` ceiling to begin with.
    """
    if min_chunk_size <= 0 or not chunks:
        return chunks

    def fits(combined_text: str) -> bool:
        return chunk_size is None or length_function(combined_text) <= chunk_size

    merged: list[Chunk] = []

    for c in chunks:
        too_small = length_function(c.text) < min_chunk_size

        if too_small and merged:
            prev = merged[-1]
            start = min(prev.start_offset, c.start_offset)
            end = max(prev.end_offset, c.end_offset)
            combined = text[start:end]

            if fits(combined):
                prev.text = combined
                prev.start_offset = start
                prev.end_offset = end
                continue

        merged.append(c)

    # A small first chunk has no earlier chunk to merge into during the
    # pass above, so fold it forward into the chunk that follows it here.
    if len(merged) > 1:
        first_too_small = length_function(merged[0].text) < min_chunk_size
        if first_too_small:
            first, second = merged[0], merged[1]
            start = min(first.start_offset, second.start_offset)
            end = max(first.end_offset, second.end_offset)
            combined = text[start:end]

            if fits(combined):
                second.text = combined
                second.start_offset = start
                second.end_offset = end
                merged.pop(0)

    for i, c in enumerate(merged):
        c.index = i

    return merged
