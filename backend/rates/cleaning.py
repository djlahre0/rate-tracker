"""Normalization and validation.

Pure functions (no DB, no I/O), so each of the seed's data issues gets a fast,
isolated unit test. Both the bulk ingestion pipeline and the ingest webhook run
rows through clean_and_validate, keeping the cleaning rules in one place.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings

from .constants import KNOWN_CURRENCIES, PROVIDER_DISPLAY, RATE_TYPES, RejectReason

_CURRENCY_ALIASES = {
    "usd": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "usd$": "USD",
    "$": "USD",
}


@dataclass
class RawRate:
    """An uncleaned record as read from any source.

    reject_reason lets a source flag a row it already knows is untrustworthy (a
    failed HTTP scrape, an unparseable id) before cleaning runs, so the row is
    still landed and quarantined instead of dropped.
    """

    provider: str
    rate_type: str
    rate_value: object
    effective_date: dt.date | None
    observed_at: dt.datetime | None
    source_url: str | None
    response_id: str
    currency: object
    payload: dict
    reject_reason: str | None = None


@dataclass
class CleanResult:
    """The verdict for one row plus its normalized fields."""

    is_valid: bool
    error_code: str | None
    slug: str
    canonical_name: str
    rate_type: str
    rate_value: Decimal | None
    currency: str | None
    effective_date: dt.date | None
    observed_at: dt.datetime | None


def normalize_provider_slug(raw: str) -> str:
    """Collapse casing and whitespace so HSBC / Hsbc / hsbc map to one identity."""
    return " ".join((raw or "").strip().lower().split())


def canonical_provider_name(slug: str) -> str:
    """Resolve a slug to a human display name (acronym-aware)."""
    return PROVIDER_DISPLAY.get(slug, slug.title())


def normalize_currency(raw: object) -> str | None:
    """Fold USD / usd / US Dollar into the ISO code USD.

    Unknown values come back upper-cased in full (not truncated to 3 chars), so
    clean_and_validate can whitelist-check them instead of fabricating a wrong
    code like "Pound" -> "POU".
    """
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    return _CURRENCY_ALIASES.get(key, str(raw).strip().upper())


def clean_and_validate(raw: RawRate, today: dt.date) -> CleanResult:
    """Normalize a raw row and decide whether it's fit to promote.

    Rejection reasons (quarantined, not dropped): blank provider, unknown rate
    type, null/unparseable/non-positive/outlier rate, future effective date.
    """
    slug = normalize_provider_slug(raw.provider)
    name = canonical_provider_name(slug)
    rate_type = (raw.rate_type or "").strip()
    currency = normalize_currency(raw.currency)

    def reject(code: str) -> CleanResult:
        return CleanResult(
            is_valid=False,
            error_code=code,
            slug=slug,
            canonical_name=name,
            rate_type=rate_type,
            rate_value=None,
            currency=currency,
            effective_date=raw.effective_date,
            observed_at=raw.observed_at,
        )

    # Honour a reject_reason the source already set (failed scrape, unparseable id)
    # so the row is landed and quarantined rather than trusted.
    if raw.reject_reason:
        return reject(raw.reject_reason)
    if not slug:
        return reject(RejectReason.BLANK_PROVIDER)
    if rate_type not in RATE_TYPES:
        return reject(RejectReason.UNKNOWN_RATE_TYPE)
    if raw.rate_value is None:
        return reject(RejectReason.NULL_RATE)
    try:
        value = Decimal(str(raw.rate_value))
    except (InvalidOperation, ValueError, TypeError):
        return reject(RejectReason.BAD_RATE_VALUE)
    if not value.is_finite():
        return reject(RejectReason.BAD_RATE_VALUE)
    if value <= 0:
        return reject(RejectReason.NON_POSITIVE_RATE)
    # Clamp the configurable ceiling to the column width (numeric(6,4) holds < 100)
    # so a mis-set RATE_OUTLIER_CEILING can't admit a value that overflows the column.
    ceiling = min(Decimal(str(settings.RATE_OUTLIER_CEILING)), Decimal("99.9999"))
    if value > ceiling:
        return reject(RejectReason.OUTLIER_RATE)
    # Unknown currency is quarantined, not coerced into a wrong 3-letter code.
    if currency is not None and currency not in KNOWN_CURRENCIES:
        return reject(RejectReason.UNKNOWN_CURRENCY)
    # effective_date and observed_at are NOT NULL in the DB, so reject missing dates
    # here; a null would otherwise crash the batch insert mid-promotion.
    if raw.effective_date is None:
        return reject(RejectReason.MISSING_EFFECTIVE_DATE)
    if raw.observed_at is None:
        return reject(RejectReason.MISSING_OBSERVED_AT)
    if raw.effective_date > today:
        return reject(RejectReason.FUTURE_EFFECTIVE_DATE)

    return CleanResult(
        is_valid=True,
        error_code=None,
        slug=slug,
        canonical_name=name,
        rate_type=rate_type,
        rate_value=value.quantize(Decimal("0.0001")),
        currency=currency or "USD",
        effective_date=raw.effective_date,
        observed_at=raw.observed_at,
    )
