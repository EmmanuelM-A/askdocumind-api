"""
Root conftest — ensures required environment variables are set before any test
module imports src.config.configs (which validates required fields on load).

Load order (highest wins):
  1. System environment variables
  2. .env file values (real credentials for integration tests)
  3. Test defaults below (safe fallbacks so unit tests can import settings)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Pull in real credentials from .env without overriding anything already in the
# process environment. Integration tests then pick up the real DATABASE_URL etc.
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file, override=False)

# Fallback test defaults — only applied when the key is still unset after .env.
os.environ.setdefault("ENV", "test")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("USER_SESSION_SECRET", "test-secret-key-not-for-production")
os.environ.setdefault("USER_CLEANUP_ENABLED", "false")
os.environ.setdefault("SEARCH_API_KEY", "test-search-api-key")
os.environ.setdefault("SEARCH_ENGINE_ID", "test-search-engine-id")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')
