"""
Factory method to get the appropriate database repository for a given model.
"""

from typing import Type, TypeVar
from src.database.connection import get_database_connection
from src.database.models import Base, Document, ChatSession, ChatMessage
from src.database.repository.database_repository import DatabaseRepository
from src.database.repository.document_repository import DocumentRepository
from src.database.repository.chat_session_repository import ChatSessionRepository
from src.database.repository.chat_message_repository import ChatMessageRepository
from src.logger.base_logger import BaseLogger

# Type variable for the model
T = TypeVar("T", bound=Base)

_logger = BaseLogger(__name__)

_database_repositories = {
    Document: DocumentRepository(
        connection=get_database_connection(), model=Document, logger=_logger
    ),
    ChatSession: ChatSessionRepository(
        connection=get_database_connection(), model=ChatSession, logger=_logger
    ),
    ChatMessage: ChatMessageRepository(
        connection=get_database_connection(), model=ChatMessage, logger=_logger
    ),
}


def get_database_repository(model: Type[T]) -> DatabaseRepository[T]:
    """
    Factory method to get the appropriate database repository
    for a given model.

    :param model: The model class to get a repository for.
    :return: The repository instance for the given model.
    :raises ValueError: If no repository is found for the model.
    """
    repository = _database_repositories.get(model)

    if repository is None:
        raise ValueError(f"No repository found for model: {model.__name__}")

    return repository
