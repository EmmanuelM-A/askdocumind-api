"""
Factory method to get the appropriate database repository for a given model.
"""

from typing import Type, TypeVar
from src.database.models import Base, Document, ChatSession, ChatMessage
from src.database.repository.database_repository import DatabaseRepository
from src.database.repository.document_repository import DocumentRepository
from src.database.repository.chat_session_repository import ChatSessionRepository
from src.database.repository.chat_message_repository import ChatMessageRepository

# Type variable for the model
T = TypeVar("T", bound=Base)

_database_repositories = {
    Document: DocumentRepository(model=Document),
    ChatSession: ChatSessionRepository(model=ChatSession),
    ChatMessage: ChatMessageRepository(model=ChatMessage),
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
