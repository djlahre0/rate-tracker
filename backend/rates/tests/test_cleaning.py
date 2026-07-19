import datetime as dt
from decimal import Decimal

import pytest

from rates.cleaning import (
    RawRate,
    canonical_provider_name,
    clean_and_validate,
    normalize_currency,
    normalize_provider_slug,
)

TODAY = dt.date(2026, 7, 19)


def raw(**overrides) -> RawRate:
    base = dict(
        provider="Chase",
        rate_type="5yr_arm_mortgage",
        rate_value=6.6,
        effective_date=dt.date(2025, 5, 15),
        observed_at=dt.datetime(2025, 5, 15, tzinfo=dt.timezone.utc),
        source_url="https://x",
        response_id="id-1",
        currency="USD",
        payload={},
    )
    base.update(overrides)
    return RawRate(**base)


@pytest.mark.parametrize(
    "value,slug",
    [("HSBC", "hsbc"), ("Hsbc", "hsbc"), ("  hsbc ", "hsbc"), ("Bank of America", "bank of america")],
)
def test_provider_casing_normalized(value, slug):  # issue 1
    assert normalize_provider_slug(value) == slug


def test_provider_canonical_display_handles_acronyms():
    assert canonical_provider_name("hsbc") == "HSBC"
    assert canonical_provider_name("pnc bank") == "PNC Bank"
    assert canonical_provider_name("chase") == "Chase"


@pytest.mark.parametrize("value", ["USD", "usd", "US Dollar", " usd "])
def test_currency_normalized(value):  # issue 2
    assert normalize_currency(value) == "USD"


def test_null_rate_rejected():  # issue 3
    result = clean_and_validate(raw(rate_value=None), TODAY)
    assert not result.is_valid and result.error_code == "null_rate"


def test_negative_rate_rejected():  # issue 4
    result = clean_and_validate(raw(rate_value=-1.84), TODAY)
    assert not result.is_valid and result.error_code == "non_positive_rate"


def test_outlier_rate_rejected():  # issue 5
    result = clean_and_validate(raw(rate_value=97.4), TODAY)
    assert not result.is_valid and result.error_code == "outlier_rate"


def test_future_effective_date_rejected():  # issue 6
    result = clean_and_validate(raw(effective_date=dt.date(2026, 9, 22)), TODAY)
    assert not result.is_valid and result.error_code == "future_effective_date"


def test_unknown_rate_type_rejected():
    result = clean_and_validate(raw(rate_type="crypto_yield"), TODAY)
    assert not result.is_valid and result.error_code == "unknown_rate_type"


def test_blank_provider_rejected():
    result = clean_and_validate(raw(provider="   "), TODAY)
    assert not result.is_valid and result.error_code == "blank_provider"


def test_valid_row_passes_with_normalized_fields():
    result = clean_and_validate(raw(provider="Hsbc", currency="US Dollar", rate_value=5.38), TODAY)
    assert result.is_valid
    assert result.slug == "hsbc" and result.canonical_name == "HSBC"
    assert result.currency == "USD"
    assert result.rate_value == Decimal("5.38")


def test_missing_effective_date_rejected():
    # A null date must be quarantined, never promoted (it is NOT NULL in the DB).
    result = clean_and_validate(raw(effective_date=None), TODAY)
    assert not result.is_valid and result.error_code == "missing_effective_date"


def test_missing_observed_at_rejected():
    result = clean_and_validate(raw(observed_at=None), TODAY)
    assert not result.is_valid and result.error_code == "missing_observed_at"


def test_nan_rate_rejected():
    result = clean_and_validate(raw(rate_value=float("nan")), TODAY)
    assert not result.is_valid and result.error_code == "bad_rate_value"


def test_non_numeric_rate_rejected():
    result = clean_and_validate(raw(rate_value="abc"), TODAY)
    assert not result.is_valid and result.error_code == "bad_rate_value"


def test_outlier_boundary_at_ceiling_passes():
    # Exactly at the 25% ceiling is allowed; only strictly above is an outlier.
    result = clean_and_validate(raw(rate_value=25), TODAY)
    assert result.is_valid


def test_effective_date_equal_to_today_passes():
    result = clean_and_validate(raw(effective_date=TODAY), TODAY)
    assert result.is_valid


def test_unknown_currency_quarantined_not_fabricated():
    # "Pound" is not a valid ISO code, so it's quarantined rather than coerced to "POU".
    result = clean_and_validate(raw(currency="Pound"), TODAY)
    assert not result.is_valid and result.error_code == "unknown_currency"


def test_known_non_usd_currency_passes():
    result = clean_and_validate(raw(currency="eur"), TODAY)
    assert result.is_valid and result.currency == "EUR"


def test_missing_currency_defaults_to_usd():
    result = clean_and_validate(raw(currency=None), TODAY)
    assert result.is_valid and result.currency == "USD"


def test_source_supplied_reject_reason_is_honored():
    from rates.constants import RejectReason

    result = clean_and_validate(raw(reject_reason=RejectReason.SCRAPE_FAILED), TODAY)
    assert not result.is_valid and result.error_code == "scrape_failed"
