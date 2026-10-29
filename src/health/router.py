"""
This module defines the health check endpoints for the API and database.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.database.dependencies import get_session_manager
from src.database.session import DatabaseSessionManager
from src.middleware.rate_limiter import health_db_limit, health_server_limit
from src.response.delivery import send_success_response

health_check_router = APIRouter(prefix="/health", tags=["Health Checks"])


@health_check_router.get("/server", summary="API Server Health Check")
@health_server_limit
def server_health_check(request: Request) -> JSONResponse:
    """
    Checks the health of the server (API) and returns a success response
    if the server is healthy.
    """
    return send_success_response(
        message="API Server health check completed.",
        status_code=status.HTTP_200_OK,
        data={"status": "OK"},
    )


@health_check_router.get("/db", summary="Database Health Check")
@health_db_limit
async def database_health_check(
    request: Request,
    session_manager: Annotated[DatabaseSessionManager, Depends(get_session_manager)],
) -> JSONResponse:
    """
    Checks the health of the database connection and returns a success
    response if the database is reachable and operational.
    """
    await session_manager.ping()

    return send_success_response(
        message="Database connectivity check completed.",
        status_code=status.HTTP_200_OK,
        data={"status": "OK"},
    )
