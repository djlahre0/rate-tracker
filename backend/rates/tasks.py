"""Celery tasks.

The scheduled ingest_rates task re-runs ingestion on a cadence (Celery Beat).
There's no live rate API, so it reads the seed file via SeedFileSource as the
scrape stand-in; the resilient HttpRateSource path is built and mock-tested, ready
to point at a real endpoint. Ingestion is idempotent, so repeated runs are safe.
"""

import datetime as dt
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .cache import invalidate_latest
from .ingestion import ingest
from .sources import SeedFileSource

log = logging.getLogger("rates.ingest")


def _seed_path() -> Path:
    return Path(settings.BASE_DIR).parent / "data" / "rates_seed.parquet"


def _scheduled_since() -> dt.date | None:
    """Bound the scheduled re-ingest to a window (free-tier deploy).

    A fixed SEED_SINCE date wins (robust for the static seed); otherwise a
    clock-relative SEED_SINCE_DAYS; otherwise None (full history, local default).
    """
    fixed = getattr(settings, "SEED_SINCE", "")
    if fixed:
        return dt.date.fromisoformat(fixed)
    days = getattr(settings, "SEED_SINCE_DAYS", 0)
    return timezone.localdate() - dt.timedelta(days=days) if days and days > 0 else None


@shared_task(name="rates.tasks.ingest_rates", bind=True, max_retries=3, default_retry_delay=30)
def ingest_rates(self):
    try:
        stats = ingest(
            SeedFileSource(
                str(_seed_path()),
                since=_scheduled_since(),
                batch_size=settings.INGEST_BATCH_SIZE,
            )
        )
        invalidate_latest()
        return stats.as_dict()
    except Exception as exc:  # pragma: no cover - retry path
        log.exception("ingest_rates_failed")
        raise self.retry(exc=exc)
