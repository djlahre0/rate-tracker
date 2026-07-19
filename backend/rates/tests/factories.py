"""Small helpers for building Rate rows in API tests."""

import datetime as dt
import uuid
from decimal import Decimal

from rates.models import Provider, Rate, RawRateResponse


def make_rate(slug, rate_type, value, day, *, response_id=None, currency="USD"):
    provider, _ = Provider.objects.get_or_create(
        slug=slug, defaults={"canonical_name": slug.title()}
    )
    response_id = response_id or uuid.uuid4()
    raw = RawRateResponse.objects.create(
        response_id=response_id, payload={}, source="seed",
        status=RawRateResponse.Status.PARSED,
    )
    return Rate.objects.create(
        provider=provider,
        rate_type=rate_type,
        rate_value=Decimal(str(value)),
        currency=currency,
        effective_date=day,
        observed_at=dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.timezone.utc),
        raw_response=raw,
    )
