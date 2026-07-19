"""Environment access with fail-fast semantics.

require() raises immediately with a clear message when a required variable is
missing, so the app dies at startup rather than with a cryptic crash ten minutes
later.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

_env = environ.Env()
# Load the repo-root .env first (where .env.example / make env put it), then a
# backend-local .env as a fallback. Real process env always wins (read_env uses
# setdefault), so docker-compose env_file and shell exports take precedence.
environ.Env.read_env(BASE_DIR.parent / ".env")
environ.Env.read_env(BASE_DIR / ".env")


def require(name: str, description: str) -> str:
    """Return a required env var or raise ImproperlyConfigured with guidance."""
    value = _env.str(name, default="").strip()
    if not value:
        raise ImproperlyConfigured(f"Missing required env var {name} — {description}")
    return value


def get(name: str, default=None, cast=str):
    """Return an optional env var, cast to the given type, or the default."""
    return _env.get_value(name, cast=cast, default=default)


def db_url(name: str = "DATABASE_URL") -> dict | None:
    """Parse a DATABASE_URL-style var into a Django DATABASES entry, or None.

    Managed hosts (Railway, Neon, Heroku, …) hand out a single connection URL.
    When it's present we use it; when it isn't we fall back to the discrete
    POSTGRES_* vars that local docker-compose sets. Returns None if unset so the
    caller can choose the fallback.
    """
    url = _env.str(name, default="").strip()
    return _env.db_url_config(url) if url else None
