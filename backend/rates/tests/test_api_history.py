import datetime as dt

import pytest
from rest_framework.test import APIClient

from rates.tests.factories import make_rate

pytestmark = pytest.mark.django_db


def _seed_series(days: int, base_day: dt.date):
    for i in range(days):
        make_rate("chase", "5yr_arm_mortgage", f"{6.0 + i * 0.01:.4f}",
                  base_day + dt.timedelta(days=i))


def test_history_requires_provider_and_type():
    r = APIClient().get("/api/rates/history?provider=chase")
    assert r.status_code == 400


def test_history_returns_paginated_shape():
    # Seed away from the today-boundary so a UTC/local day skew can't drop a point.
    _seed_series(10, dt.date.today() - dt.timedelta(days=12))
    r = APIClient().get("/api/rates/history?provider=chase&type=5yr_arm_mortgage")
    body = r.json()
    assert r.status_code == 200
    assert set(body.keys()) == {"count", "next", "previous", "results"}
    assert body["count"] == 10


def test_history_caps_limit_at_max():
    # Seed 501 rows across 60 distinct days (<=366-day window) so a huge `limit`
    # genuinely proves the cap: exactly max_limit (500) come back and `next` is set.
    import uuid as _uuid
    from decimal import Decimal

    from rates.models import Provider, Rate, RawRateResponse

    provider, _ = Provider.objects.get_or_create(
        slug="chase", defaults={"canonical_name": "Chase"}
    )
    base = dt.date(2025, 1, 1)
    raws = [
        RawRateResponse(response_id=_uuid.uuid4(), payload={}, source="seed", status="parsed")
        for _ in range(501)
    ]
    RawRateResponse.objects.bulk_create(raws)
    Rate.objects.bulk_create(
        [
            Rate(
                provider=provider, rate_type="5yr_arm_mortgage", rate_value=Decimal("6.0"),
                currency="USD", effective_date=base + dt.timedelta(days=i % 60),
                observed_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(hours=i),
                raw_response_id=raws[i].response_id,
            )
            for i in range(501)
        ]
    )
    r = APIClient().get(
        "/api/rates/history?provider=chase&type=5yr_arm_mortgage"
        "&from=2025-01-01&to=2025-03-31&limit=99999"
    )
    body = r.json()
    assert r.status_code == 200
    assert body["count"] == 501
    assert len(body["results"]) == 500  # clamped to max_limit, not unbounded
    assert body["next"] is not None  # more remain, so the cap really bit


def test_history_filters_by_from_to():
    base = dt.date(2025, 1, 1)
    _seed_series(30, base)
    r = APIClient().get(
        "/api/rates/history?provider=chase&type=5yr_arm_mortgage&from=2025-01-01&to=2025-01-10"
    )
    assert r.status_code == 200
    assert r.json()["count"] == 10


def test_history_rejects_window_over_cap():
    r = APIClient().get(
        "/api/rates/history?provider=chase&type=5yr_arm_mortgage&from=2020-01-01&to=2025-01-01"
    )
    assert r.status_code == 400


def test_history_open_ended_from_older_than_cap_clamps_instead_of_400():
    # Only `from` (far in the past); `to` defaults to today. The window exceeds the
    # cap, but an open-ended "since <date>" query should clamp to the most-recent
    # max window and return 200 — not reject.
    recent = dt.date.today() - dt.timedelta(days=3)
    make_rate("chase", "5yr_arm_mortgage", "6.0", recent)
    far = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    r = APIClient().get(f"/api/rates/history?provider=chase&type=5yr_arm_mortgage&from={far}")
    assert r.status_code == 200
    assert r.json()["count"] == 1  # the in-window recent row


def test_history_unknown_granularity_is_400():
    make_rate("chase", "5yr_arm_mortgage", "6.0", dt.date(2025, 1, 1))
    r = APIClient().get(
        "/api/rates/history?provider=chase&type=5yr_arm_mortgage&granularity=weekly"
    )
    assert r.status_code == 400  # a typo is a 400, not silent raw intraday data
    assert r.json()["error"] == "validation_error"


def test_history_unknown_provider_is_404():
    make_rate("chase", "5yr_arm_mortgage", "6.0", dt.date(2025, 1, 1))
    r = APIClient().get("/api/rates/history?provider=nosuchbank&type=5yr_arm_mortgage")
    assert r.status_code == 404  # silent empty result would hide the mistyped slug


def test_history_default_window_anchors_to_latest_available_data():
    # Data ends well in the past; a today-anchored default window would be empty.
    old = dt.date(2025, 1, 15)
    for i in range(5):
        make_rate("chase", "5yr_arm_mortgage", f"{6 + i * 0.01:.4f}", old + dt.timedelta(days=i))
    r = APIClient().get("/api/rates/history?provider=chase&type=5yr_arm_mortgage")
    assert r.status_code == 200
    assert r.json()["count"] == 5  # anchored to latest data, not empty


def test_history_daily_collapses_intraday_to_latest_point():
    import uuid
    from decimal import Decimal

    from rates.models import Provider, Rate, RawRateResponse

    provider, _ = Provider.objects.get_or_create(
        slug="chase", defaults={"canonical_name": "Chase"}
    )
    day = dt.date(2025, 3, 10)
    for hour, value in [(8, "6.0"), (12, "6.2"), (20, "6.5")]:
        raw = RawRateResponse.objects.create(
            response_id=uuid.uuid4(), payload={}, source="seed", status="parsed"
        )
        Rate.objects.create(
            provider=provider, rate_type="5yr_arm_mortgage", rate_value=Decimal(value),
            currency="USD", effective_date=day,
            observed_at=dt.datetime(2025, 3, 10, hour, tzinfo=dt.timezone.utc), raw_response=raw,
        )
    r = APIClient().get(
        "/api/rates/history?provider=chase&type=5yr_arm_mortgage"
        "&granularity=daily&from=2025-03-01&to=2025-03-31"
    )
    body = r.json()
    assert body["count"] == 1  # three intraday readings collapse to one daily point
    assert body["results"][0]["rate_value"] == "6.5000"  # the latest observation (20:00)
