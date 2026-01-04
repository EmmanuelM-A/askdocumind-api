"""
Handles chatbot interactions using Retrieval-Augmented Generation (RAG).
"""

from typing import List, Any, Sequence, Optional

from fastapi import UploadFile

from src.components.chatbot.query_handler import QueryHandler
from src.components.ingestion.document_processor import DocumentProcessor
from src.components.retrieval.embedder import Embedder
from src.components.retrieval.vector_store import VectorStore
from src.components.retrieval.web_searcher import WebSearcher
from src.config.configs import settings
from src.config.constants import Source
from src.errors.custom_exceptions import throw_not_found_error, throw_server_error
from src.logger.base_logger import BaseLogger
from src.services.validation.rag_validation import sanitize_query


class RAGChatbot:
    """Defines all methods related to RAG Chatbot interactions."""

    def __init__(
        self,
        vector_store: VectorStore,
        document_processor: DocumentProcessor,
        embedder: Embedder,
        query_handler: QueryHandler,
        web_searcher: WebSearcher,
    ) -> None:
        """
        Initializes the RAGChatbot with its components.

        :param vector_store: The vector store instance.
        :param document_processor: The document processor instance.
        :param embedder: The embedder instance.
        :param query_handler: The query handler instance.
        :param web_searcher: The web searcher instance.
        """
        self.vector_store = vector_store
        self.document_processor = document_processor
        self.embedder = embedder
        self.query_handler = query_handler
        self.web_searcher = web_searcher
        self._logger = BaseLogger(__name__)

    # ========================== CHATBOT METHODS ==========================

    def create_chat(self, index_chat_id: Optional[str]) -> str:
        """
        Creates a new chat by creating a new vector index.

        :param index_chat_id: The ID of the index to create.
        :return: The ID of the created index.
        """
        return self.vector_store.create_vector_index(index_chat_id)

    def get_chat(self, index_chat_id: str) -> Any:
        """
        Retrieves a chat by its index ID.

        :param index_chat_id: The ID of the index to retrieve.
        :return: The index object.
        """
        return self.vector_store.get_vector_index(index_chat_id)

    def get_chats(self, index_chat_ids: Optional[List[str]] = None) -> List[Any]:
        """
        Retrieves multiple chats by their index IDs.

        :param index_chat_ids: A list of index IDs to retrieve. If None,
            retrieves all indexes.
        :return: A list of index objects.
        """
        return self.vector_store.get_vector_indexes(index_chat_ids)

    def delete_chat(self, index_chat_id: str) -> None:
        """Deletes a chat by its index ID."""

        self.vector_store.delete_vector_index(index_chat_id)

    def delete_chats(self, index_chat_ids: Optional[List[str]] = None) -> None:
        """Deletes multiple chats by their index IDs."""

        self.vector_store.delete_vector_indexes(index_chat_ids)

    def chat_exists(self, index_chat_id: str) -> bool:
        """Checks if a chat exists by its index ID."""

        return self.vector_store.vector_index_exists(index_chat_id)

    # ========================== VECTOR METHODS ==========================

    def process_and_save_vectors(self, files: List[UploadFile], index_id: str) -> None:
        """Processes documents, creates embeddings, and saves them to the vector store."""

        self._check_if_index_exist(index_id)

        total_chunks = 0

        # Stream document chunks → stream embedding batches
        for vectors, metadata in self.embedder.embed_documents(
            documents=self.document_processor.process(files)
        ):
            self.vector_store.add_vectors(
                index_id=index_id,
                vectors=vectors,
                metadata=metadata,
            )
            total_chunks += len(vectors)

        self._logger.info(
            f"{total_chunks} document chunks processed and saved to "
            f"the index '{index_id}'."
        )

    def get_current_vectors(self, index_id: str) -> tuple[Sequence, list[dict]] | Any:
        """Gets current vectors and metadata from the vector store based on index ID."""

        self._check_if_index_exist(index_id)

        return self.vector_store.load_vectors(index_id)

    def delete_current_vectors(self, index_chat_id: str) -> None:
        """Deletes vectors from the vector store."""

        self.vector_store.delete_vectors(index_chat_id)

    # ========================== QUERY METHODS ==========================

    def process_query(
        self, query: str, index_id: str, web_search_enabled: bool = False
    ) -> dict:
        """
        Processes a user query by searching the vector store and optionally
        performing a web search if no relevant results are found.

        :param query: The user query string.
        :param index_id: The ID of the index to search.
        :param web_search_enabled: The flag to enable web search if no results
            are found in the vector store.
        :return: A dictionary containing the answer, sources, and source type.
        """

        self._check_if_index_exist(index_id)

        index, metadata = self.vector_store.load_vectors(index_id)

        sanitized_query = sanitize_query(query, self._logger)

        results = self.query_handler.search_for_vector(sanitized_query, index, metadata)

        self._logger.debug(
            f"Search returned {len(results) if results else 0} results for "
            f"the query '{sanitized_query}'."
        )

        if not results and web_search_enabled:
            self._logger.info(
                f"No results found in vector store for query: '{sanitized_query}'. "
                "Attempting web search..."
            )

            if not settings.web.IS_WEB_SEARCH_ENABLED:
                throw_server_error(
                    message="Web search is disabled in the system settings.",
                    error_code="WEB_SEARCH_DISABLED",
                )

            web_results = self.web_searcher.process_query_via_web_search(
                query=sanitized_query, index_id=index_id
            )

            response_data = None

            if web_results:
                response_data = self.query_handler.generate_responses(
                    query=sanitized_query, retrieved_chunks=web_results
                )

            if response_data:
                response_data["source_type"] = Source.WEB_SEARCH
                self._logger.info(
                    f"Generated response from web search for the query: "
                    f"'{sanitized_query}'."
                )
                return response_data

        else:
            response_data = self.query_handler.generate_responses(
                query=sanitized_query, retrieved_chunks=results
            )

            if response_data:
                response_data["source_type"] = Source.UPLOAD
                self._logger.info(f"Generated response for query: '{sanitized_query}'.")
                return response_data

        # No results found anywhere
        response_data = {
            "answer": "I couldn't find relevant information to answer your "
            "question in my documents or through web search. Please "
            "try rephrasing your question or ask about a different "
            "topic.",
            "sources": [],
            "source_type": "none",
        }

        self._logger.info(
            f"No relevant information found for the query: '{sanitized_query}'."
        )
        return response_data

    # ======================= HELPER METHODS =======================

    def _check_if_index_exist(self, index_id: str) -> None:
        """
        Checks if the specified index exists in the vector store.

        Args:
            index_id (str): The ID of the index to check.

        Raises:
            NotFoundError: If the index does not exist.
        """

        exists = self.vector_store.vector_index_exists(index_id)

        if not exists:
            throw_not_found_error(
                message=f"Index with ID {index_id} not found.",
                error_code="INDEX_NOT_FOUND",
            )

        self._logger.debug(f"Index with ID {index_id} exists.")

    def _search_web(self):
        pass
