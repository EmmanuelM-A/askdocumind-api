"""
Defines the WebSearcher interface for web search and content processing.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable

from src.rag.schemas.retrieval import WebResult


class WebSearcher(ABC):
    """
    Defines the interface for a web search service, which is responsible for
    performing web searches and processing the resulting content into embedding
    vectors.
    """

    @abstractmethod
    async def search_web(self, query: str) -> list[WebResult]:
        """Return the web search content for a query."""
        raise NotImplementedError

    @abstractmethod
    async def search_web_stream(self, query: str) -> AsyncIterable[WebResult]:
        """Return the web search content for a query as an async iterable."""
        raise NotImplementedError
