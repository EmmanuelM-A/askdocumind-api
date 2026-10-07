"""
Factory method to get the appropriate database repository for a given model.
"""

from typing import Literal, TypeAlias, overload

from src.database.session import get_database_connection
from src.uploads.repository.interfaces import DBTransactionFactory
from src.uploads.repository.interfaces import (
    ChatMessageRepositoryInterface,
)
from src.uploads.repository.interfaces import (
    ChatSessionRepositoryInterface,
)
from src.uploads.repository.interfaces import (
    DocumentChunkRepositoryInterface,
)
from src.uploads.repository.interfaces.document_repository import (
    DocumentRepositoryInterface,
)
from src.uploads.repository.interfaces import UserRepositoryInterface
from src.uploads.repository.sqlalchemy import (
    ChatMessageRepository,
    ChatSessionRepository,
    DocumentRepository,
    SQLAlchemyDBTransactionFactory,
    UserRepository,
)
from src.uploads.repository.sqlalchemy import (
    DocumentChunkRepository,
)

_database_repositories = {
    "DOCUMENT": DocumentRepository(connection=get_database_connection()),
    "DOCUMENT_CHUNK": DocumentChunkRepository(connection=get_database_connection()),
    "CHAT_SESSION": ChatSessionRepository(connection=get_database_connection()),
    "CHAT_MESSAGE": ChatMessageRepository(connection=get_database_connection()),
    "USER": UserRepository(connection=get_database_connection()),
}

_db_transaction_factory: DBTransactionFactory | None = None

RepositoryModelKey: TypeAlias = Literal[
    "DOCUMENT", "CHAT_SESSION", "CHAT_MESSAGE", "USER", "DOCUMENT_CHUNK"
]


@overload
def get_database_repository(
    model: Literal["DOCUMENT"],
) -> DocumentRepositoryInterface: ...
@overload
def get_database_repository(
    model: Literal["CHAT_SESSION"],
) -> ChatSessionRepositoryInterface: ...
@overload
def get_database_repository(
    model: Literal["CHAT_MESSAGE"],
) -> ChatMessageRepositoryInterface: ...
@overload
def get_database_repository(model: Literal["USER"]) -> UserRepositoryInterface: ...
@overload
def get_database_repository(
    model: Literal["DOCUMENT_CHUNK"],
) -> DocumentChunkRepositoryInterface: ...
def get_database_repository(
    model: RepositoryModelKey,
) -> (
    DocumentRepositoryInterface
    | ChatSessionRepositoryInterface
    | ChatMessageRepositoryInterface
    | UserRepositoryInterface
    | DocumentChunkRepositoryInterface
):
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
