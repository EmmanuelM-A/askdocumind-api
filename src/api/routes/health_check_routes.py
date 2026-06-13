"""
Routes for health check endpoints.
Provides API and database health diagnostics.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette import status
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response
from src.database.connection import get_database_connection

health_check_router = APIRouter(prefix="/health", tags=["Health Checks"])


@health_check_router.get("/api", summary="API Health Check")
def api_health_check() -> JSONResponse:
    """
    Returns API health status.
    """

    response_model = SuccessResponseModel(
        message="The API is healthy and running.",
        data={"status": "OK"},
    )

    return create_success_response(
        status_code=status.HTTP_200_OK, success_response_model=response_model
    )


@health_check_router.get("/db", summary="Database Health Check")
async def database_health_check() -> JSONResponse:
    """
    Returns database connectivity status.
    """

    await get_database_connection().ping_database()

    response_model = SuccessResponseModel(
        message="Database connectivity check completed.",
        data={"status": "OK"},
    )

    return create_success_response(
        status_code=status.HTTP_200_OK, success_response_model=response_model
    )
