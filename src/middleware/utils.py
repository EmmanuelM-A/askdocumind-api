"""
Helpers shared by the ASGI middlewares.
"""

from starlette.types import Scope


def get_route_path(scope: Scope) -> str:
    """
    Return the request path without the app's root_path or a trailing slash,
    so it matches the paths the routes are declared with.
    """
    path = scope["path"]
    root_path = scope.get("root_path", "")

    if root_path and (path == root_path or path.startswith(f"{root_path}/")):
        path = path[len(root_path) :]

    return path.rstrip("/") or "/"
