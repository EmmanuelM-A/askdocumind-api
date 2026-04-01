"""
Responsible for handling user queries and generating their corresponding
response.
"""

import numpy as np
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from src.config.configs import settings
from src.components.prompts.prompt_loader import create_prompt_template
from src.components.retrieval.embedder import Embedder

from src.errors.custom_exceptions import unprocessable_entity_error
from src.logger.base_logger import BaseLogger

logger = BaseLogger(__name__)


def sanitize_query(query: str, logger: BaseLogger) -> str:
    """Lazy sanitizer proxy to keep this module patch-friendly in tests."""
    from src.api.services.validation.rag_validation import sanitize_query as _sanitize

    return _sanitize(query=query, logger=logger)


class QueryHandler:
    """
    Handles the query processing and the response generation.
    """

    def __init__(self, embedder: Embedder) -> None:
        """
        Initializes the QueryHandler instance.

        Args:
            embedder: The class instance used to create embeddings for indexes.
        """
        self.embedder = embedder
        self.llm_model_name = settings.llm.LLM_MODEL_NAME

    def search_for_vector(self, query: str, index, metadata):
        """
        Embeds query, searches vector DB, returns top_k results.
        """

        if index is None:
            raise unprocessable_entity_error(
                message="FAISS index is required", error_code="MISSING_FAISS_INDEX"
            )

        if metadata is None or not isinstance(metadata, (dict, list)):
            raise unprocessable_entity_error(
                message="Valid metadata dictionary or list is required",
                error_code="INVALID_METADATA",
            )


        query = sanitize_query(query=query, logger=logger)

        logger.debug("Embedding queries now...")

        query_vector = self.embedder.embed_query(query)

        logger.debug("Initialing vector search...")

        # Retrieve the top-K nearest neighbor indices for the query vector
        _, indices = index.search(
            np.array([query_vector]).astype("float32"), settings.llm.RETRIEVAL_TOP_K
        )

        if not indices.any():
            logger.error(f"No indices found for the query vector: {query_vector}")
            return None

        results = []

        for i in indices[0]:
            try:
                entry = metadata[i]
            except (KeyError, IndexError, TypeError):
                logger.warning(f"No metadata entry found at index {i}.")
                continue

            if not isinstance(entry, dict):
                logger.warning(f"Invalid metadata entry type at index {i}: {type(entry)}")
                continue

            text = entry.get("text")
            meta = entry.get("meta")

            if text is None or meta is None:
                logger.error(f"Missing 'text' or 'meta' in entry at index {i}.")
                continue

            results.append({"text": text, "meta": meta})

        if not results:
            logger.error(f"No results found for the query: {query}")
            return None

        logger.info(f"Results found for the query: {query}")

        return results

    @staticmethod
    def __extract_source_from_metadata(metadata):
        """Safely extract source from metadata regardless of type."""

        try:
            # Handle FileDocumentMetadata objects
            if hasattr(metadata, "source"):
                source = getattr(metadata, "source", None)
                return source if source else None

            # Handle dictionary metadata
            if isinstance(metadata, dict):
                return metadata.get("source", None)

            # Handle string metadata (edge case)
            if isinstance(metadata, str):
                return metadata

            logger.warning(f"Unexpected metadata type: {type(metadata)}")
            return None

        except (AttributeError, KeyError, TypeError) as e:
            logger.warning(f"Error extracting source from metadata: {e}")
            return None

    def generate_responses(self, query: str, retrieved_chunks):
        """
        Formats a prompt with the query and retrieved chunks, then passes it
        to an LLM.
        """

        if not retrieved_chunks:
            logger.warning("No retrieved chunks provided for response generation.")
            return None

        logger.debug(f"Generating responses for the query: {query}")

        llm = ChatOpenAI(
            model=self.llm_model_name, temperature=settings.llm.LLM_TEMPERATURE
        )

        context_text = "\n\n".join([chunk["text"] for chunk in retrieved_chunks])

        prompt_template = create_prompt_template(settings.llm.RESPONSE_PROMPT_FILEPATH)

        # Create a chain for processing
        rag_chain = prompt_template | llm | StrOutputParser()

        response = rag_chain.invoke({"context": context_text, "query": query})

        if response.strip() == "NEED_WEB_SEARCH":
            return None

        sources = []
        for chunk in retrieved_chunks:
            try:
                metadata = chunk["meta"]

                source = self.__extract_source_from_metadata(metadata)

                if source:
                    sources.append(source)
                else:
                    logger.debug(f"No source found in metadata: {type(metadata)}")

            except (KeyError, AttributeError, TypeError) as e:
                logger.warning(f"Could not extract source from chunk metadata: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error extracting source from metadata: {e}")
                continue

        logger.debug("Extracted the sources from the chunks successfully")

        # Remove duplicates
        sources = list(set(sources))

        logger.debug("Response generated by LLM.")

        return {"answer": response, "sources": sources}
