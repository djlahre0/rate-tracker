import datetime as dt
import uuid

import pytest
from rest_framework.test import APIClient

from rates.cache import latest_key
from rates.tests.factories import make_rate
from django.core.cache import cache

pytestmark = pytest.mark.django_db


def test_latest_returns_most_recent_per_provider_type():
    make_rate("chase", "5yr_arm_mortgage", "6.0", dt.date(2025, 1, 1))
    make_rate("chase", "5yr_arm_mortgage", "6.5", dt.date(2025, 2, 1))

    response = APIClient().get("/api/rates/latest?type=5yr_arm_mortgage")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["provider"] == "Chase"
    assert body[0]["provider_slug"] == "chase"
    assert body[0]["rate_value"] == "6.5000"


def test_latest_without_type_returns_row_per_provider_and_type():
    make_rate("chase", "5yr_arm_mortgage", "6.5", dt.date(2025, 2, 1))
    make_rate("hsbc", "savings_1yr_fixed", "4.7", dt.date(2025, 2, 1))

    response = APIClient().get("/api/rates/latest")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_latest_is_cached_after_first_request():
    make_rate("chase", "5yr_arm_mortgage", "6.5", dt.date(2025, 2, 1))
    assert cache.get(latest_key("5yr_arm_mortgage")) is None

    APIClient().get("/api/rates/latest?type=5yr_arm_mortgage")

    assert cache.get(latest_key("5yr_arm_mortgage")) is not None


def test_latest_rejects_unknown_type():
    response = APIClient().get("/api/rates/latest?type=nonsense")
    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
