import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError

from rates.models import Provider, Rate, RawRateResponse

pytestmark = pytest.mark.django_db


def test_provider_slug_unique():
    Provider.objects.create(slug="hsbc", canonical_name="HSBC")
    with pytest.raises(IntegrityError):
        Provider.objects.create(slug="hsbc", canonical_name="Hsbc")


def test_rate_links_to_raw_and_provider():
    provider = Provider.objects.create(slug="chase", canonical_name="Chase")
    response_id = uuid.uuid4()
    raw = RawRateResponse.objects.create(
        response_id=response_id, payload={}, source="seed",
        status=RawRateResponse.Status.PARSED,
    )
    rate = Rate.objects.create(
        provider=provider,
        rate_type="5yr_arm_mortgage",
        rate_value=Decimal("6.6080"),
        currency="USD",
        effective_date=dt.date(2025, 5, 15),
        observed_at=dt.datetime(2025, 5, 15, 19, 34, tzinfo=dt.timezone.utc),
        raw_response=raw,
    )
    assert rate.raw_response.response_id == response_id
    assert provider.rates.count() == 1


def test_rate_one_to_one_raw_enforced():
    provider = Provider.objects.create(slug="chase", canonical_name="Chase")
    response_id = uuid.uuid4()
    raw = RawRateResponse.objects.create(
        response_id=response_id, payload={}, source="seed",
        status=RawRateResponse.Status.PARSED,
    )
    common = dict(
        provider=provider, rate_type="5yr_arm_mortgage", rate_value=Decimal("6.0"),
        currency="USD", effective_date=dt.date(2025, 1, 1),
        observed_at=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
    )
    Rate.objects.create(raw_response=raw, **common)
    with pytest.raises(IntegrityError):
        Rate.objects.create(raw_response=raw, **common)
