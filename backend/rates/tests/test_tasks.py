from pathlib import Path

import pytest

from rates import tasks
from rates.models import Rate

pytestmark = pytest.mark.django_db

SEED_FIXTURE = Path(__file__).parent / "fixtures" / "rates_fixture.parquet"


def test_ingest_rates_task_runs_and_reports(monkeypatch):
    monkeypatch.setattr(tasks, "_seed_path", lambda: SEED_FIXTURE)
    result = tasks.ingest_rates.run()
    assert result["landed"] == 12
    assert result["promoted"] == 8
    assert Rate.objects.count() == 8


def test_ingest_rates_task_invalidates_latest_cache(monkeypatch):
    # The scheduled write path must bust the cache, just like the webhook does.
    from django.core.cache import cache

    from rates.cache import latest_key

    monkeypatch.setattr(tasks, "_seed_path", lambda: SEED_FIXTURE)
    cache.set(latest_key("5yr_arm_mortgage"), [{"stale": True}], 300)
    tasks.ingest_rates.run()
    assert cache.get(latest_key("5yr_arm_mortgage")) is None


def test_scheduled_since_prefers_fixed_date_over_days(settings):
    import datetime as dt

    settings.SEED_SINCE = "2026-01-01"
    settings.SEED_SINCE_DAYS = 30
    assert tasks._scheduled_since() == dt.date(2026, 1, 1)


def test_scheduled_since_none_when_unbounded(settings):
    settings.SEED_SINCE = ""
    settings.SEED_SINCE_DAYS = 0
    assert tasks._scheduled_since() is None
