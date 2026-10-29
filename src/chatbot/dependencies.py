from typing import Annotated

from fastapi import Depends

from src.chatbot.services.chatbot_service import ChatbotService, LLMConfig
from src.config.configs import settings
from src.rag.dependencies import get_rag_retrieval_service
from src.rag.services.retrieve import RetrieveChunkEmbeddingService
from src.shared.prompts import load_prompt_from


def get_chatbot_service(
    retrieval_service: Annotated[
        RetrieveChunkEmbeddingService, Depends(get_rag_retrieval_service)
    ],
) -> ChatbotService:
    """
    Provide a ChatbotService instance for the current request.
    """
    return ChatbotService(
        retrieval_service=retrieval_service,
        llm_config=LLMConfig(
            prompt_template=load_prompt_from(path=settings.llm.ANSWER_PROMPT_TEMPLATE)
        ),
    )
