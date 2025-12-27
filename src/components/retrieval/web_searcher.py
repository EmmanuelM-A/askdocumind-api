"""
Web search module for retrieving information from the internet when no
relevant documents are found.
"""

import requests
import time
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from src.components.ingestion.document_processor import DocumentProcessor
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.vector_store import VectorStore
from src.config.configs import settings
from src.components.ingestion.document import FileDocument, FileDocumentMetadata
from src.logger.base_logger import BaseLogger


class WebSearcher:
    """
    Handles web search functionality and content retrieval.
    """

    def __init__(
        self,
        embedder: Embedder,
        document_processor: DocumentProcessor,
        vector_store: VectorStore,
    ) -> None:
        """
        Initializes the WebSearcher instance.
        """

        self._logger = BaseLogger(__name__)

        self.search_api_key = settings.web.SEARCH_API_KEY.get_secret_value()
        self.search_engine_id = settings.web.SEARCH_ENGINE_ID.get_secret_value()

        self.embedder = embedder
        self.document_processor = document_processor
        self.vector_store = vector_store

    # ======================== WEB SEARCH METHODS ========================

    def process_query_via_web_search(
        self, query: str, index_id: str
    ) -> Optional[List[dict]]:
        """
        Process a user query by performing a web search, retrieving content,
        embedding the content, and storing it in the vector store.

        Args:
            query: The user's search query.
            index_id: The ID of the vector index to store results in.

        Returns:
            A list of dictionaries containing the text and metadata of the
            ingested web documents, or None if no documents were found.
        """

        self._logger.info(f"Processing query via web search: '{query}'")

        web_documents = self._search_and_retrieve_content_from_web(query)

        if not web_documents:
            self._logger.info("No documents retrieved from web search")
            return None

        total_chunks = 0
        results = []

        web_chunks = self.document_processor.process(web_documents)

        # Stream chunks → batch embeddings → store vectors
        for vectors, metadata in self.embedder.embed_documents(web_chunks):
            self.vector_store.add_vectors(
                index_id=index_id,
                vectors=vectors,
                metadata=metadata,
            )

            total_chunks += len(vectors)

        for doc in web_chunks:
            results.append({"text": doc.content, "metadata": doc.metadata})

        self._logger.info(
            f"Ingested {total_chunks} web document chunks into index '{index_id}'"
        )

        return results

    # ========================== HELPER METHODS ==========================

    def _search_and_retrieve_content_from_web(self, query: str) -> List[FileDocument]:
        """Enhanced web search with better error handling."""

        if not query or not query.strip():
            self._logger.error("Empty query provided to web search")
            return []

        self._logger.debug(f"Starting web search for query: {query[:100]}")

        try:
            search_results = self._search_web(query)

            if not search_results:
                self._logger.info("No web search results found")
                return []

            documents = []
            successful_fetches = 0

            for i, result in enumerate(search_results):
                try:
                    # Validate result structure
                    if not isinstance(result, dict) or "url" not in result:
                        self._logger.warning(
                            f"Invalid search result structure at index {i}"
                        )
                        continue

                    url = result.get("url", "").strip()
                    if not url or not url.startswith(("http://", "https://")):
                        self._logger.warning(f"Invalid URL in search result: {url}")
                        continue

                    # Respect rate limiting
                    if i > 0:
                        time.sleep(settings.web.WEB_REQUEST_DELAY_SECS)

                    document = self._fetch_and_create_document(result)
                    if document:
                        documents.append(document)
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

    def _search_web(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform web search using Google Custom Search API.

        Args:
            query: The search query string

        Returns:
            List of search results with title, snippet, and url.
        """

        num_results: int = settings.web.MAX_WEB_SEARCH_RESULTS

        # Validate API credentials
        if not self.search_api_key or not self.search_engine_id:
            self._logger.critical("Search API credentials not configured")
            return self._fallback_search(query, num_results)

        self._logger.debug(f"Performing web search for: {query}")

        try:
            # Google Custom Search API endpoint
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.search_api_key,
                "cx": self.search_engine_id,
                "q": query,
                "num": min(num_results, settings.web.MAX_WEB_REQUEST_RESULTS),
            }

            # Make the API request
            response = requests.get(
                url, params=params, timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS
            )
            response.raise_for_status()

            # Parse the JSON response
            data = response.json()

            if "items" not in data:
                self._logger.warning("No search results found")
                return []

            results = []
            for item in data["items"]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("link", ""),
                    }
                )

            self._logger.info(f"Retrieved {len(results)} search results")

            return results

        except Exception as e:
            self._logger.error(f"Error in web search: {e}")
            return self._fallback_search(query, num_results)

    def _fallback_search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """
        Fallback search using DuckDuckGo (no API key required).

        Note: This is a simple implementation. For production, consider using
        dedicated libraries like `duckduckgo-search` or similar.
        """

        if not settings.web.WEB_SEARCH_FALLBACK_ENABLED:
            self._logger.warning("Web search fallback is disabled")
            return []

        self._logger.info(f"Using fallback search method for the query: '{query}'")

        try:
            # Simple DuckDuckGo search (note: this may not work reliably in production)
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {"User-Agent": settings.web.WEB_USER_AGENT}

            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            results = []

            # Parse DuckDuckGo results (simplified)
            result_elements = soup.find_all("div", class_="result")[:num_results]

            for element in result_elements:
                title_elem = element.find("a", class_="result__a")
                snippet_elem = element.find("div", class_="result__snippet")

                if title_elem and snippet_elem:
                    results.append(
                        {
                            "title": title_elem.get_text(strip=True),
                            "snippet": snippet_elem.get_text(strip=True),
                            "url": title_elem.get("href", ""),
                            "source": "duckduckgo_search",
                        }
                    )

            self._logger.info(f"Retrieved {len(results)} fallback search results")
            return results

        except Exception as e:
            self._logger.error(f"Error in fallback search: {e}")
            return []

    def _fetch_and_create_document(self, result: dict) -> Optional[FileDocument]:
        """
        Safely fetch and create document from search result.

        Args:
            result: A single search result dictionary

        Returns:
            FileDocument object or None if failed
        """

        try:
            url = result["url"]
            title = result.get("title", "Untitled")
            snippet = result.get("snippet", "")

            content = self._fetch_page_content(url)

            if content and len(content.strip()) >= settings.web.MIN_WEB_CONTENT_LENGTH:
                full_content = (
                    f"Title: {title}\n\nSummary: {snippet}\n\nContent: {content}"
                )
            else:
                # Fallback to snippet if content fetch fails or is too short
                full_content = f"Title: {title}\n\nSummary: {snippet}"
                self._logger.debug(f"Using snippet fallback for {url}")

            metadata = FileDocumentMetadata(
                filename=title or "web_content",
                file_extension=".html",
                author=None,
                source=url,
            )

            return FileDocument(full_content, metadata)

        except Exception as e:
            self._logger.error(f"Error creating document from search result: {e}")
            return None

    def _fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract text content from a web page.

        Args:
            url: URL to fetch

        Returns:
            Extracted text content or None if failed
        """

        try:
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
