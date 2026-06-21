"""
Web search module for retrieving information from the internet when no
relevant documents are found.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse
from uuid import UUID

import requests
import time
from typing import List, Optional
from bs4 import BeautifulSoup

from src.components.ingestion.vector_processor import VectorProcessor
from src.components.retrieval.embedder import Embedder
from src.config.configs import settings
from src.database.repository.interfaces import DBTransaction
from src.logger.base_logger import BaseLogger


@dataclass
class WebContent:
    content: str
    source: str


@dataclass
class WebSearchResult:
    title: str
    snippet: str
    url: str


class WebSearcher:
    """
    Handles web search functionality and content retrieval.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_processor: VectorProcessor,
    ) -> None:
        """
        Initializes the WebSearcher instance.
        """

        self._logger = BaseLogger(__name__)

        self.brave_api_key = settings.web.BRAVE_SEARCH_API_KEY.get_secret_value()

        self.embedder = embedder
        self._vector_processor = vector_processor

    # ======================== WEB SEARCH METHODS ========================

    async def search_and_ingest_web_content(
        self, query: str, chat_session_id: UUID, tx: Optional[DBTransaction] = None
    ) -> int:

        self._logger.debug(f"Processing query via web search: '{query}'")

        raw_web_documents = self._search_and_retrieve_content_from_web(query)

        if not raw_web_documents:
            self._logger.info("No documents retrieved from web search")
            return 0

        all_web_content: List[str] = []
        all_content_sources: List[str] = []

        for raw_web_document in raw_web_documents:
            all_web_content.append(raw_web_document.content)
            all_content_sources.append(raw_web_document.source)

        ingested = await self._vector_processor.process_and_save_vectors_from_web(
            chat_session_id=chat_session_id, raw_web_contents=all_web_content, tx=tx
        )

        self._logger.info(
            f"Ingested {ingested} web chunks for query '{query}' into chat {chat_session_id}"
        )
        return ingested

    # ========================== HELPER METHODS ==========================

    def _search_and_retrieve_content_from_web(self, query: str) -> List[WebContent]:
        """Enhanced web search with better error handling."""

        if not query or not query.strip():
            self._logger.error("Empty query provided to web search")
            return []

        self._logger.debug(f"Starting web search for query: {query[:100]}")

        try:
            search_results = self._search_web(query)

            if not search_results or len(search_results) == 0:
                self._logger.info("No web search results found")
                return []

            documents: List[WebContent] = []
            successful_fetches = 0

            for i, result in enumerate(search_results):
                try:

                    url = result.url.strip()
                    if not url or not url.startswith(("http://", "https://")):
                        self._logger.warning(f"Invalid URL in search result: {url}")
                        continue

                    # Respect rate limiting
                    if i > 0:
                        time.sleep(settings.web.WEB_REQUEST_DELAY_SECS)

                    document_content = self._fetch_and_full_content(result)
                    if document_content:
                        documents.append(
                            WebContent(
                                content=document_content,
                                source=url,
                            )
                        )
                        successful_fetches += 1

                except Exception as e:
                    self._logger.error(f"Error processing search result {i}: {e}")
                    continue

            self._logger.info(
                f"Web search completed: {successful_fetches}/{len(search_results)} successful"
            )
            return documents

        except Exception as e:
            self._logger.error(f"Critical error in web search: {e}", exc_info=True)
            return []

    def _search_web(self, query: str) -> List[WebSearchResult]:
        """
        Perform web search using Brave Search API.

        Args:
            query: The search query string

        Returns:
            List of search results with title, snippet, and url.
        """

        num_results: int = min(settings.web.MAX_WEB_SEARCH_RESULTS, 20)

        if not self.brave_api_key:
            self._logger.critical("Brave Search API key not configured")
            return self._fallback_search(query, num_results)

        self._logger.debug(f"Performing web search for: {query}")

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.brave_api_key,
            }
            params = {"q": query, "count": num_results}

            response = requests.get(
                url, headers=headers, params=params, timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS
            )
            response.raise_for_status()

            data = response.json()
            items = data.get("web", {}).get("results", [])

            if not items:
                self._logger.warning("No search results found")
                return []

            results: List[WebSearchResult] = [
                WebSearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("description", ""),
                    url=item.get("url", ""),
                )
                for item in items
            ]

            self._logger.debug(f"Retrieved {len(results)} search results")

            return results

        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else "<no response body>"
            self._logger.error(f"Error in web search: {e}, response body: {body}")
            return self._fallback_search(query, num_results)
        except Exception as e:
            self._logger.error(f"Error in web search: {e}")
            return self._fallback_search(query, num_results)

    def _fallback_search(self, query: str, num_results: int) -> List[WebSearchResult]:
        """
        Fallback search using DuckDuckGo (no API key required).

        Note: This is a simple implementation. For production, consider using
        dedicated libraries like `duckduckgo-search` or similar.
        """

        if not settings.web.WEB_SEARCH_FALLBACK_ENABLED:
            self._logger.warning("Web search fallback is disabled")
            return []

        try:
            # Simple DuckDuckGo search (note: this may not work reliably in production)
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {"User-Agent": settings.web.WEB_USER_AGENT}

            response = requests.get(search_url, headers=headers, timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            results: List[WebSearchResult] = []

            # Parse DuckDuckGo results (simplified)
            result_elements = soup.find_all("div", class_="result")[:num_results]

            for element in result_elements:
                title_elem = element.find("a", class_="result__a")
                snippet_elem = element.find("div", class_="result__snippet")

                if title_elem and snippet_elem:
                    results.append(
                        WebSearchResult(
                            title=title_elem.get_text(strip=True),
                            snippet=snippet_elem.get_text(strip=True),
                            url=str(title_elem.get("href", "")),
                        )
                    )

            self._logger.debug(f"Retrieved {len(results)} fallback search results")
            return results

        except Exception as e:
            self._logger.error(f"Error in fallback search: {e}")
            return []

    def _fetch_and_full_content(self, result: WebSearchResult) -> Optional[str]:
        """
        Safely fetch and extract content from a web page given a search result,
        with robust error handling and fallback to snippet if content retrieval
        fails.
        """

        try:
            url = result.url
            title = result.title
            snippet = result.snippet

            content = self._fetch_page_content(url)

            if content and len(content.strip()) >= settings.app.MIN_DOCUMENT_CONTENT_LENGTH:
                full_content = (
                    f"Title: {title}\n\nSummary: {snippet}\n\nContent: {content}"
                )
            else:
                # Fallback to snippet if content fetch fails or is too short
                full_content = f"Title: {title}\n\nSummary: {snippet}"
                self._logger.debug(f"Using snippet fallback for {url}")

            return full_content

        except Exception as e:
            self._logger.error(f"Error creating document from search result: {e}")
            return None

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Return False if the URL resolves to a private or reserved IP address."""
        try:
            hostname = urlparse(url).hostname
            if not hostname:
                return False
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            )
        except Exception:
            return False

    def _fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract text content from a web page at the given URL or
        return None if any error occurs.
        """

        try:
            if not self._is_safe_url(url):
                self._logger.warning(f"Blocked fetch to private/reserved address: {url}")
                return None

            headers = {"User-Agent": settings.web.WEB_USER_AGENT}

            response = requests.get(
                url, headers=headers, timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Extract text from main content areas
            content_selectors = [
                "main",
                "article",
                ".content",
                ".post-content",
                ".entry-content",
                ".article-content",
                "p",
            ]

            content_text = ""
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    content_text = " ".join(
                        [elem.get_text(strip=True) for elem in elements]
                    )
                    break

            if not content_text:
                # Fallback to body text
                body = soup.find("body")
                if body:
                    content_text = body.get_text(strip=True)

            # Clean up the text
            content_text = " ".join(content_text.split())

            self._logger.debug(
                f"Successfully extracted {len(content_text)} characters from {url}"
            )
            return content_text

        except Exception as e:
            self._logger.error(f"Error fetching content from {url}: {e}")
            return None
