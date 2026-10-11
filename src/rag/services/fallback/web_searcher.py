"""
Defines the WebSearcher interface for web search and content processing.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable


class WebSearcher(ABC):
    """
    Defines the interface for a web search service, which is responsible for
    performing web searches and processing the resulting content into embedding
    vectors.
    """

    @abstractmethod
    async def search_web(self, query: str) -> list[str]:
        """Return the web search content for a query."""
        raise NotImplementedError

    @abstractmethod
    async def search_web_stream(self, query: str) -> AsyncIterable[str]:
        """Return the web search content for a query as an async iterable."""
        raise NotImplementedError
