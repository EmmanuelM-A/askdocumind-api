"""
Defines the paths that are considered public and do not require authentication.
"""

HEALTH_PATHS = frozenset({"/api/health/server", "/api/health/db"})
DOCS_PATHS = frozenset({"/docs", "/openapi.json", "/redoc"})
PUBLIC_PATHS = HEALTH_PATHS | DOCS_PATHS
