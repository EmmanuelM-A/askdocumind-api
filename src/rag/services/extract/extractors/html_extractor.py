from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup, Tag, NavigableString

from src.exceptions import unprocessable_content_error
from src.rag.services.extract.extractors.extractor import (
    Extractor,
    Segment,
    group_blocks,
)

_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

# Tags that end the current line of text. Text directly inside one of these
# tags is kept, even when the tag also contains other blocks.
_BLOCK_TAGS = frozenset(
    {
        "p",
        "li",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
        "blockquote",
        "td",
        "th",
        "tr",
        "table",
        "figure",
        "figcaption",
        "div",
        "section",
        "article",
        "main",
        "header",
        "details",
        "summary",
        "address",
    }
)

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
    "head",
    # Form controls. The <form> tag itself is kept, because some sites wrap
    # the whole page in one and its text would be lost.
    "button",
    "select",
    "textarea",
]


def _clean(pieces: list[str]) -> str:
    """Join pieces of inline text, collapse whitespace, and empty the list."""
    text = " ".join("".join(pieces).split())
    pieces.clear()
    return text


def _page_title(soup: BeautifulSoup) -> str:
    # An SVG icon can carry its own <title>, which is not the page title.
    for tag in soup.find_all("title"):
        if tag.find_parent("svg") is None:
            return " ".join(tag.get_text().split())
    return ""


def _walk(root: Tag) -> Iterator[tuple[str, bool]]:
    """
    Yield (text, is_heading) blocks in document order.

    The walk uses a stack instead of recursion, so deeply nested markup
    cannot hit the recursion limit.
    """
    pieces: list[str] = []
    stack: list[tuple[Iterator, bool]] = [(iter(root.children), False)]

    while stack:
        children, is_block = stack[-1]
        node = next(children, None)

        if node is None:
            stack.pop()
            if is_block:
                text = _clean(pieces)
                if text:
                    yield text, False
            continue

        if isinstance(node, Tag):
            name = node.name

            if name in _HEADING_TAGS or name == "pre" or name in _BLOCK_TAGS:
                pending = _clean(pieces)
                if pending:
                    yield pending, False

            if name in _HEADING_TAGS:
                text = " ".join(node.get_text().split())
                if text:
                    yield f"{'#' * int(name[1])} {text}", True
            elif name == "pre":
                text = node.get_text().strip("\n")
                if text.strip():
                    yield text, False
            else:
                stack.append((iter(node.children), name in _BLOCK_TAGS))

        elif type(node) is NavigableString:
            # Comments, doctypes and other special strings are skipped.
            pieces.append(str(node))

    text = _clean(pieces)
    if text:
        yield text, False


def _blocks(soup: BeautifulSoup) -> Iterator[tuple[str, bool]]:
    title = _page_title(soup)

    for tag in soup(_REMOVED_TAGS):
        tag.decompose()

    for line_break in soup("br"):
        line_break.replace_with("\n")

    blocks = _walk(soup.body or soup)
    first = next(blocks, None)

    # Skip the title when the page opens with a heading that says the same.
    duplicate = (
        first is not None
        and first[1]
        and first[0].lstrip("#").strip().casefold() == title.casefold()
    )

    if title and not duplicate:
        yield f"# {title}", True

    if first is not None:
        yield first
        yield from blocks


def html_to_text(html: str) -> str:
    """Return the readable text of an HTML page, one block per paragraph."""
    soup = BeautifulSoup(html, "lxml")
    return "\n\n".join(text for text, _ in _blocks(soup))


class HtmlExtractor(Extractor):
    """Text extractor for HTML documents."""

    def extract(self, path: Path) -> Iterator[Segment]:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise unprocessable_content_error(
                message="The HTML file could not be read.",
                error_code="HTML_EXTRACTION_ERROR",
                cause=exc,
            ) from exc

        try:
            # Passing bytes lets BeautifulSoup read the declared encoding.
            soup = BeautifulSoup(data, "lxml")
        except Exception as exc:
            raise unprocessable_content_error(
                message="The HTML file could not be parsed.",
                error_code="HTML_EXTRACTION_ERROR",
                cause=exc,
            ) from exc

        yield from group_blocks(_blocks(soup))
