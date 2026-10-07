from fastapi import Depends

from src.config.configs import settings
from src.database.implementations.sqlalchemy_db_transaction import (
    DBTransactionFactoryImpl,
)
from src.database.interfaces.db_transactions import DBTransactionFactory
from src.database.session import DatabaseSessionManager

_database_session_manager: DatabaseSessionManager


def get_session_manager() -> DatabaseSessionManager:
    """
    Returns a singleton instance of DatabaseSessionManager. Initializes it
    if not already done.
    """
    global _database_session_manager

    if _database_session_manager is None:
        _database_session_manager = DatabaseSessionManager(
            database_url=settings.database.DATABASE_URL.get_secret_value()
        )

    return _database_session_manager


def get_tx_factory(
    session_manager: DatabaseSessionManager = Depends(get_session_manager),
) -> DBTransactionFactory:
    """
    Returns an instance of the DBTransactionFactoryImpl.
    """
    return DBTransactionFactoryImpl(session_manager=session_manager)
