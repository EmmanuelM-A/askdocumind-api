"""
Routes for health check endpoints.
Provides API and database health diagnostics.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from slowapi.util import get_remote_address
from starlette import status
from src.api.middleware.rate_limiter import limiter, health_api_limit, health_db_limit
from src.api.utils.api_responses import SuccessResponseModel
from src.api.utils.response_delivery import create_success_response
from src.database.connection import get_database_connection

health_check_router = APIRouter(prefix="/health", tags=["Health Checks"])


@health_check_router.get("/api", summary="API Health Check")
@limiter.limit(health_api_limit, key_func=get_remote_address)
def api_health_check(request: Request) -> JSONResponse:
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
@limiter.limit(health_db_limit, key_func=get_remote_address)
async def database_health_check(request: Request) -> JSONResponse:
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
