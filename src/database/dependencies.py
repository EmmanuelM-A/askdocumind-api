from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import DatabaseSessionManager


async def get_session_manager(request: Request) -> DatabaseSessionManager:
    """
    Dependency function to get the session manager from the app state.
    """
    return request.app.state.session_manager


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session (from the app's session
    manager).
    """
    async with request.app.state.session_manager.get_session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
