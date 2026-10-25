import logging
import re
from uuid import UUID

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.chatbot.schemas.chatbot import (
    ChatbotResponse,
    ChatRequest,
    DocumentSource,
    Source,
    WebSource,
)
from src.config.configs import settings
from src.exceptions import server_error
from src.rag.schemas.retrieval import GetChunkEmbeddings, RetrievalResults
from src.rag.services.retrieve import RetrieveChunkEmbeddingService

_logger = logging.getLogger(__name__)

_NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information to answer your question "
    "in the uploaded documents. Please try rephrasing your "
    "question or ask about a different topic."
)

# The prompt treats everything inside these tags as data. Text that contains
# them could close a wrapper early, so they are removed from the inputs.
_WRAPPER_TAG = re.compile(r"</?(?:sources?|question)\b[^>]*>", re.IGNORECASE)

# Citations such as [1], [2][4] and [1, 3].
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


class LLMConfig(BaseModel):

    prompt_template: ChatPromptTemplate


class ChatbotService:

    def __init__(
        self,
        retrieval_service: RetrieveChunkEmbeddingService,
        llm_config: LLMConfig,
        llm: Runnable | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        # The OpenAI client already retries connection errors, rate limits
        # and server errors, so the chain does not add its own retry.
        self._llm: Runnable = (
            llm
            if llm is not None
            else ChatOpenAI(
                model=settings.llm.MODEL_NAME,
                temperature=settings.llm.TEMPERATURE,
                timeout=settings.llm.REQUEST_TIMEOUT_SECS,
                max_retries=settings.llm.MAX_RETRIES,
                max_completion_tokens=settings.llm.MAX_OUTPUT_TOKENS,
            )
        )
        self._chain = llm_config.prompt_template | self._llm | StrOutputParser()

    async def handle_chat_request(
        self,
        data: ChatRequest,
        chat_session_id: UUID,
        authenticated_user_id: UUID,
    ) -> ChatbotResponse:
        # retrieve() checks that the user owns the chat session.
        results = await self._retrieval_service.retrieve(
            data=GetChunkEmbeddings(query=data.query, configs=data.configs),
            chat_session_id=chat_session_id,
            authenticated_user_id=authenticated_user_id,
        )

        context, sources = _build_context(results)

        if not sources:
            return ChatbotResponse(answer=_NO_CONTEXT_ANSWER, sources=[])

        try:
            answer = await self._chain.ainvoke(
                {
                    "sources": context,
                    "question": _WRAPPER_TAG.sub("", data.query).strip(),
                }
            )
        except Exception as e:
            _logger.exception(
                "Failed to generate an answer for chat session '%s'", chat_session_id
            )
            raise server_error(
                message="The answer could not be generated. Please try again.",
                error_code="ANSWER_GENERATION_FAILED",
                cause=e,
            ) from e

        return ChatbotResponse(answer=answer, sources=_cited_sources(answer, sources))


def _build_context(results: RetrievalResults) -> tuple[str, list[Source]]:
    """
    Number the document chunks and then the web results in rank order, and
    stop once the next one would go over the context budget. The position of
    a source in the returned list matches its id in the context.
    """
    entries: list[tuple[Source, str]] = [
        (
            DocumentSource(document_id=chunk.document_id, chunk_index=chunk.chunk_index),
            chunk.chunk_text,
        )
        for chunk in results.chunks
    ]
    entries.extend(
        (WebSource(url=result.url, title=result.title), result.content)
        for result in results.additional
    )

    blocks: list[str] = []
    sources: list[Source] = []
    budget = settings.llm.MAX_CONTEXT_CHARS

    for source, text in entries:
        text = _WRAPPER_TAG.sub("", text).strip()

        if not text:
            continue

        if len(text) > budget:
            break

        budget -= len(text)
        sources.append(source)
        blocks.append(
            f'<source id="{len(sources)}" type="{source.type}">\n{text}\n</source>'
        )

    return "\n\n".join(blocks), sources


def _cited_sources(answer: str, sources: list[Source]) -> list[Source]:
    """Keep only the sources the answer cites, in id order."""
    cited = {
        int(number) for group in _CITATION.findall(answer) for number in group.split(",")
    }
    return [source for index, source in enumerate(sources, start=1) if index in cited]
