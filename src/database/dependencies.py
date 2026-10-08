from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get a database session (from the app's session
    manager).
    """
    async with request.app.state.session_manager.get_session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
