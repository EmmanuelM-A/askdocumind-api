"""
Routes for health check endpoints.
Provides API and database health diagnostics.
"""

from fastapi import APIRouter
from src.api.controllers.health_check_controller import HealthCheckController

health_check_router = APIRouter(prefix="/health", tags=["Health Check"])


@health_check_router.get("/api", summary="API Health Check")
async def api_health_check():
    """
    Returns API uptime and health status.
    """

    return await HealthCheckController.get_api_health()


@health_check_router.get("/db", summary="Database Health Check")
async def database_health_check():
    """
    Checks database connectivity and returns status.
    """

    return await HealthCheckController.get_database_health()
