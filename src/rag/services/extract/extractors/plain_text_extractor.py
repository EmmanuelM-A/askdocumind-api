import codecs
from collections.abc import Iterator
from pathlib import Path

from charset_normalizer import from_path

from src.config.configs import settings
from src.rag.services.extract.extractors.extractor import (
    Extractor,
    Segment,
    group_blocks,
)


def _detect_encoding(path: Path) -> str:
    """
    Return utf-8-sig when the file decodes cleanly, else the best detected
    encoding.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        with path.open("rb") as file:
            while block := file.read(settings.rag.READ_BLOCK_BYTES):
                decoder.decode(block)
        decoder.decode(b"", final=True)
        return "utf-8-sig"
    except UnicodeDecodeError:
        match = from_path(path).best()
        return match.encoding if match else settings.rag.FALLBACK_ENCODING


class PlainTextExtractor(Extractor):
    """Text extractor for TXT, Markdown, and code files."""

    def extract(self, path: Path) -> Iterator[Segment]:
        encoding = _detect_encoding(path)

        with path.open(encoding=encoding, errors="replace") as file:
            yield from group_blocks(
                ((line.rstrip("\r\n"), False) for line in file),
                separator="\n",
            )
