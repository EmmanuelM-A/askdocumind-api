from src.config.configs import settings
from src.database.session import DatabaseSessionManager

_database_session_manager: DatabaseSessionManager


def get_database_session() -> DatabaseSessionManager:
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
