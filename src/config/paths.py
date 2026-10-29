"""
Defines the paths that are considered public and do not require authentication.

Paths are relative to the app's root_path ('/api'), as the routes declare them.
"""

HEALTH_PATHS = frozenset({"/health/server", "/health/db"})
DOCS_PATHS = frozenset({"/docs", "/openapi.json", "/redoc"})
PUBLIC_PATHS = HEALTH_PATHS | DOCS_PATHS
