"""
Root conftest — sets minimum required environment variables before any test
module imports src.config.configs (which validates required fields on load).
"""

import os

# Core
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")

# Database
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")

# Auth
os.environ.setdefault("USER_SESSION_SECRET", "test-secret-key-not-for-production")

# Anonymous session cleanup
os.environ.setdefault("USER_CLEANUP_ENABLED", "false")

# Web search (not used in unit tests, but required to load settings)
os.environ.setdefault("SEARCH_API_KEY", "test-search-api-key")
os.environ.setdefault("SEARCH_ENGINE_ID", "test-search-engine-id")

# CORS
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')
