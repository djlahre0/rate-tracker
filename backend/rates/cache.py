"""Cache keys and invalidation for the read endpoints (/rates/latest, /rates/summary).

Write-through invalidation: every write (ingest webhook, scheduled ingestion)
deletes the cached read keys, so reads are never stale beyond one request. The
short TTL on each cached value is only a safety net for a missed invalidation.
Keys are namespaced under rates:latest: and rates:summary:.

The full set of keys is small and known (the unfiltered view plus one per rate
type, for each endpoint), so invalidation deletes them explicitly with
delete_many, avoiding a dependency on django-redis's delete_pattern (Django's
built-in RedisCache has no such method).
"""

from __future__ import annotations

from django.core.cache import cache

from .constants import RATE_TYPES

LATEST_PREFIX = "rates:latest:"
SUMMARY_PREFIX = "rates:summary:"
LATEST_TTL_SECONDS = 300
SUMMARY_TTL_SECONDS = 300


def latest_key(rate_type: str | None) -> str:
    return f"{LATEST_PREFIX}{rate_type or 'all'}"


def summary_key(rate_type: str | None) -> str:
    return f"{SUMMARY_PREFIX}{rate_type or 'all'}"


def _all_latest_keys() -> list[str]:
    return [latest_key(None)] + [latest_key(t) for t in RATE_TYPES]


def _all_summary_keys() -> list[str]:
    return [summary_key(None)] + [summary_key(t) for t in RATE_TYPES]


def invalidate_latest() -> None:
    """Drop every cached read variant (the unfiltered view and each ?type=).

    Covers both /rates/latest and /rates/summary, which share the same
    write-through invalidation: any write that changes the latest rate also
    changes its summary (delta + sparkline), so both are busted together.
    """
    cache.delete_many(_all_latest_keys() + _all_summary_keys())
