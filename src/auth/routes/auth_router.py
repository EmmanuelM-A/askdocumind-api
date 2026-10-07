from fastapi import APIRouter

auth_router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@auth_router.post(
    path="/anonymous/init",
    summary="Initialize an anonymous session",
)
async def init_anonymous_session():
    pass
