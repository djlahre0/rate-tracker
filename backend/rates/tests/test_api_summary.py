"""Tests for GET /api/rates/summary — latest + 30-day change + sparkline per series."""

import datetime as dt

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from rates.cache import summary_key
from rates.tests.factories import make_rate

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def _days_ago(n: int) -> dt.date:
    return TODAY - dt.timedelta(days=n)


def test_summary_returns_one_row_per_series_with_latest_value():
    make_rate("chase", "5yr_arm_mortgage", "6.0", _days_ago(20))
    make_rate("chase", "5yr_arm_mortgage", "6.5", _days_ago(2))  # latest

    response = APIClient().get("/api/rates/summary?type=5yr_arm_mortgage")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    row = body[0]
    assert row["provider"] == "Chase"
    assert row["provider_slug"] == "chase"
    assert row["rate_value"] == "6.5000"  # the most recent, not the oldest


def test_summary_change_and_sparkline_track_the_window():
    make_rate("chase", "5yr_arm_mortgage", "6.0", _days_ago(20))
    make_rate("chase", "5yr_arm_mortgage", "6.2", _days_ago(10))
    make_rate("chase", "5yr_arm_mortgage", "6.5", _days_ago(1))

    row = APIClient().get("/api/rates/summary?type=5yr_arm_mortgage").json()[0]

    # Sparkline is oldest → newest and ends at the current value.
    assert row["spark"] == [6.0, 6.2, 6.5]
    # change_30d is last − first of the window (chip and line agree).
    assert row["change_30d"] == "0.5000"
    assert row["change_30d_pct"] == pytest.approx(0.5 / 6.0 * 100, rel=1e-4)


def test_summary_single_point_reports_null_change():
    make_rate("hsbc", "savings_1yr_fixed", "4.7", _days_ago(2))

    row = APIClient().get("/api/rates/summary?type=savings_1yr_fixed").json()[0]

    assert row["spark"] == [4.7]
    assert row["change_30d"] is None
    assert row["change_30d_pct"] is None


def test_summary_sparkline_is_capped_to_the_window():
    # 40 consecutive days; only the last 30 days fall inside the window.
    for n in range(40):
        make_rate("chase", "5yr_arm_mortgage", f"{5 + n * 0.01:.4f}", _days_ago(39 - n))

    row = APIClient().get("/api/rates/summary?type=5yr_arm_mortgage").json()[0]

    assert len(row["spark"]) <= 30
    # Ascending and ending at the newest observation.
    assert row["spark"] == sorted(row["spark"])
    assert row["spark"][-1] == pytest.approx(5 + 39 * 0.01)


def test_summary_uses_most_recent_dates_even_when_old():
    # The window is data-anchored, not calendar-based: a series whose readings are
    # all months old still gets a sparkline from its most recent dates. This mirrors
    # the seed, whose dense data ends well before "today".
    make_rate("truist", "savings_easy_access", "3.9", _days_ago(210))
    make_rate("truist", "savings_easy_access", "4.1", _days_ago(200))

    row = APIClient().get("/api/rates/summary?type=savings_easy_access").json()[0]

    assert row["rate_value"] == "4.1000"
    assert row["spark"] == [3.9, 4.1]
    assert row["change_30d"] == "0.2000"


def test_summary_filters_by_type():
    make_rate("chase", "5yr_arm_mortgage", "6.5", _days_ago(1))
    make_rate("hsbc", "savings_1yr_fixed", "4.7", _days_ago(1))

    body = APIClient().get("/api/rates/summary?type=5yr_arm_mortgage").json()

    assert len(body) == 1
    assert body[0]["rate_type"] == "5yr_arm_mortgage"


def test_summary_is_cached_after_first_request():
    make_rate("chase", "5yr_arm_mortgage", "6.5", _days_ago(1))
    assert cache.get(summary_key("5yr_arm_mortgage")) is None

    APIClient().get("/api/rates/summary?type=5yr_arm_mortgage")

    assert cache.get(summary_key("5yr_arm_mortgage")) is not None


def test_summary_rejects_unknown_type():
    response = APIClient().get("/api/rates/summary?type=nonsense")
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
