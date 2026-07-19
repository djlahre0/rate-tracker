"""Django settings for the Rate-Tracker backend.

All secrets and environment-specific values come from env vars via config.env,
which fails fast on missing required ones. See .env.example for the full list.
"""

from pathlib import Path

from config import env
from config.logging import build_logging

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core / security -------------------------------------------------------
SECRET_KEY = env.require("DJANGO_SECRET_KEY", "Django cryptographic signing key")
DEBUG = env.get("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = env.get("DJANGO_ALLOWED_HOSTS", default="*", cast=str).split(",")
# Behind a platform proxy (Railway, etc.) requests arrive over HTTP internally
# but were HTTPS at the edge; trust the forwarded scheme so request.is_secure()
# is correct. Harmless locally (the header is simply absent).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Bearer token for the authenticated ingest webhook.
INGEST_API_TOKEN = env.require("INGEST_API_TOKEN", "Bearer token for POST /api/rates/ingest")

# --- Apps / middleware -----------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "rates",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "rates.middleware.QueryTimingMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

# --- Database (PostgreSQL) --------------------------------------------------
# Prefer a single DATABASE_URL when a managed host provides one (Railway, Neon,
# …); otherwise fall back to the discrete POSTGRES_* vars local compose sets.
_db_from_url = env.db_url("DATABASE_URL")
if _db_from_url:
    _db_from_url.setdefault("CONN_MAX_AGE", 60)  # reuse connections in production
    DATABASES = {"default": _db_from_url}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env.require("POSTGRES_DB", "Postgres database name"),
            "USER": env.require("POSTGRES_USER", "Postgres user"),
            "PASSWORD": env.require("POSTGRES_PASSWORD", "Postgres password"),
            "HOST": env.get("POSTGRES_HOST", default="db"),
            "PORT": env.get("POSTGRES_PORT", default="5432"),
        }
    }

# --- Cache + Celery (Redis) ------------------------------------------------
REDIS_URL = env.require("REDIS_URL", "Redis URL for cache + Celery broker/backend")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env.get("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_BEAT_SCHEDULE = {
    "ingest-rates": {
        "task": "rates.tasks.ingest_rates",
        "schedule": float(env.get("INGEST_INTERVAL_SECONDS", default=3600, cast=int)),
    }
}

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rates.pagination.BoundedLimitOffsetPagination",
    "PAGE_SIZE": 100,
    "EXCEPTION_HANDLER": "rates.errors.structured_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

# --- CORS (frontend at :3000) ----------------------------------------------
CORS_ALLOWED_ORIGINS = env.get(
    "CORS_ALLOWED_ORIGINS", default="http://localhost:3000"
).split(",")

# --- Domain knobs ----------------------------------------------------------
# Rates above this (%) are treated as impossible outliers and quarantined.
RATE_OUTLIER_CEILING = env.get("RATE_OUTLIER_CEILING", default="25", cast=float)
# Any single SQL query slower than this (seconds) logs a warning.
SLOW_QUERY_SECONDS = env.get("SLOW_QUERY_SECONDS", default="0.2", cast=float)
# Scheduled ingestion window (keeps a free-tier deploy light; local default is the
# full history). SEED_SINCE is a fixed ISO date (robust for the static seed whose
# dense data ends well before "today"); SEED_SINCE_DAYS is a clock-relative
# fallback for a real live source. SEED_SINCE wins when both are set; empty/0 = full.
SEED_SINCE = env.get("SEED_SINCE", default="", cast=str).strip()
SEED_SINCE_DAYS = env.get("SEED_SINCE_DAYS", default=0, cast=int)
# Rows pulled from the seed parquet per batch. Peak memory scales with this: a
# whole batch is materialised as Python objects before the bulk insert. The
# default suits a dev box; a memory-capped container (a 1 GB Railway worker)
# wants ~5_000, which measured ~430 MB peak RSS vs ~590 MB at 50_000.
INGEST_BATCH_SIZE = env.get("INGEST_BATCH_SIZE", default=50_000, cast=int)

# --- Misc ------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
USE_I18N = False
STATIC_URL = "static/"
LOGGING = build_logging(DEBUG)
