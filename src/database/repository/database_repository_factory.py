"""
Factory method to get the appropriate database repository for a given model.
"""

from typing import Literal, TypeAlias, Optional

from src.database.connection import get_database_connection
from src.database.repository.interfaces import DBTransactionFactory

from src.database.repository.sqlalchemy import (
    DocumentRepository,
    ChatSessionRepository,
    ChatMessageRepository,
    UserRepository,
    SQLAlchemyDBTransactionFactory,
)

_database_repositories = {
    "DOCUMENT": DocumentRepository(connection=get_database_connection()),
    "CHAT_SESSION": ChatSessionRepository(connection=get_database_connection()),
    "CHAT_MESSAGE": ChatMessageRepository(connection=get_database_connection()),
    "USER": UserRepository(connection=get_database_connection()),
}

_db_transaction_factory: Optional[DBTransactionFactory] = None

RepositoryModelKey: TypeAlias = Literal["DOCUMENT", "CHAT_SESSION", "CHAT_MESSAGE", "USER"]


def get_database_repository(
    model: RepositoryModelKey,
) -> DocumentRepository | ChatSessionRepository | ChatMessageRepository | UserRepository:
    """
    Factory method to get the appropriate database repository instance
    for a given model.

    :param model: Repository key: "DOCUMENT", "CHAT_SESSION", "CHAT_MESSAGE", "USER".
    :return: The repository instance for the given model.
    :raises ValueError: If no repository is found for the model.
    """
    repository = _database_repositories.get(model)

    if repository is None:
        raise ValueError(f"No repository found for model key: {model}")

    return repository


def get_tx_factory() -> DBTransactionFactory:
    """Default factory method to get a database transaction factory instance."""
    global _db_transaction_factory

    if _db_transaction_factory is None:
        _db_transaction_factory = SQLAlchemyDBTransactionFactory(
            connection=get_database_connection()
        )

    return _db_transaction_factory
