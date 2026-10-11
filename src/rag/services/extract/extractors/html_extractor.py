from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup

from .extractor import Extractor, Segment, group_blocks

_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

_BLOCK_TAGS = _HEADING_TAGS + [
    "p",
    "li",
    "pre",
    "blockquote",
    "td",
    "th",
    "dt",
    "dd",
    "figcaption",
    "div",
]

_REMOVED_TAGS = [
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "nav",
    "footer",
    "aside",
    "form",
    "head",
]


def _blocks(soup: BeautifulSoup) -> Iterator[tuple[str, bool]]:
    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(_REMOVED_TAGS):
        tag.decompose()

    for line_break in soup("br"):
        line_break.replace_with("\n")

    if title:
        yield f"# {title}", True

    root = soup.body or soup
    found = False

    for element in root.find_all(_BLOCK_TAGS):
        # Skip containers. Their child blocks get read on their own turn.
        if element.find(_BLOCK_TAGS):
            continue

        if element.name == "pre":
            text = element.get_text().strip("\n")
            if text.strip():
                found = True
                yield text, False
            continue

        text = " ".join(element.get_text().split())
        if not text:
            continue

        found = True
        if element.name in _HEADING_TAGS:
            yield f"{'#' * int(element.name[1])} {text}", True
        else:
            yield text, False

    if not found:
        text = " ".join(root.get_text().split())
        if text:
            yield text, False


class HtmlExtractor(Extractor):
    """Text extractor for HTML documents."""

    def extract(self, path: Path) -> Iterator[Segment]:
        # Passing bytes lets BeautifulSoup read the declared encoding.
        soup = BeautifulSoup(path.read_bytes(), "lxml")
        yield from group_blocks(_blocks(soup))
