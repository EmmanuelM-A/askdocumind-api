"""Routes for authentication-related endpoints."""

from fastapi import APIRouter
from fastapi import Request

from src.api.controllers.auth_controller import AuthController

auth_router = APIRouter(prefix="/auth", tags=["Auth"])

_controller = AuthController()


@auth_router.post("/anonymous/", summary="Create an anonymous user session")
async def create_anonymous_user_session(request: Request):
    return await _controller.create_anonymous_user_endpoint(request)
