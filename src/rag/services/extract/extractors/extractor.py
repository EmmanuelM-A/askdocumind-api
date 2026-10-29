from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from src.config.configs import settings


@dataclass(frozen=True)
class Segment:
    text: str
    page: int | None = None
    separator: str = "\n\n"  # placed between this segment and the previous one


class Extractor(ABC):
    """
    Abstract base class for extracting text segments from files.
    """

    @abstractmethod
    def extract(self, path: Path) -> Iterator[Segment]:
        """
        Yields segments of text extracted from the file at the given path.
        """
        raise NotImplementedError(
            "The method 'extract' must be implemented by its subclasses."
        )


def group_blocks(
    blocks: Iterable[tuple[str, bool]], separator: str = "\n\n"
) -> Iterator[Segment]:
    """
    Join (text, is_heading) blocks into segments. A heading starts a new
    segment, and a segment closes once it reaches the target size.
    """
    target = settings.rag.SEGMENT_TARGET_CHARS
    buffer: list[str] = []
    size = 0

    for text, is_heading in blocks:
        if buffer and (is_heading or size >= target):
            segment = "\n".join(buffer)
            if segment.strip():
                yield Segment(text=segment, separator=separator)
            buffer, size = [], 0

        buffer.append(text)
        size += len(text) + 1

    segment = "\n".join(buffer)
    if segment.strip():
        yield Segment(text=segment, separator=separator)
