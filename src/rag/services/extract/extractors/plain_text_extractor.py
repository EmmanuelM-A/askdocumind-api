import codecs
from collections.abc import Iterator
from pathlib import Path

from charset_normalizer import from_path

from src.config.configs import settings
from src.exceptions import unprocessable_content_error
from src.rag.services.extract.extractors.extractor import (
    Extractor,
    Segment,
    group_blocks,
)

# Control bytes that do not appear in text (tab, newline, form feed and
# carriage return are allowed). A high share of them means a binary file.
_CONTROL_BYTES = bytes(range(0x09)) + bytes(range(0x0E, 0x20))
_MAX_CONTROL_RATIO = 0.05


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


def _looks_binary(path: Path, encoding: str) -> bool:
    """
    True when the start of the file is mostly control bytes. UTF-16 and
    UTF-32 text is full of NUL bytes by design, so it is never checked.
    """
    if encoding.lower().replace("_", "-").startswith(("utf-16", "utf-32")):
        return False

    with path.open("rb") as file:
        sample = file.read(settings.rag.READ_BLOCK_BYTES)

    if not sample:
        return False

    controls = len(sample) - len(sample.translate(None, _CONTROL_BYTES))
    return controls / len(sample) > _MAX_CONTROL_RATIO


class PlainTextExtractor(Extractor):
    """Text extractor for TXT, Markdown, and code files."""

    def extract(self, path: Path) -> Iterator[Segment]:
        try:
            encoding = _detect_encoding(path)

            if _looks_binary(path, encoding):
                raise unprocessable_content_error(
                    message="The file looks like binary data, not text.",
                    error_code="TEXT_EXTRACTION_ERROR",
                )

            file = path.open(encoding=encoding, errors="replace")
        except OSError as exc:
            raise unprocessable_content_error(
                message="The text file could not be read.",
                error_code="TEXT_EXTRACTION_ERROR",
                cause=exc,
            ) from exc

        with file:
            # NUL characters cannot be stored in a PostgreSQL text column.
            yield from group_blocks(
                ((line.rstrip("\r\n").replace("\x00", ""), False) for line in file),
                separator="\n",
            )
