from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    text: str
    page: int | None = None


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
