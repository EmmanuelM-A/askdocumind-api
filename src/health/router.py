"""
This module defines the health check endpoints for the API and database.
"""

from fastapi import APIRouter, status, Depends
from fastapi.responses import JSONResponse

from src.database import DatabaseSessionManager, get_session_manager
from src.response.delivery import send_success_response

health_check_router = APIRouter(prefix="/health", tags=["Health Checks"])


@health_check_router.get("/server", summary="API Server Health Check")
def server_health_check() -> JSONResponse:
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
async def database_health_check(
    session_manager: DatabaseSessionManager = Depends(get_session_manager),
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
