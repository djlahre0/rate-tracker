"""Domain constants: the known rate types and canonical provider display names."""

# The five rate products present in the seed. Unknown types are quarantined.
RATE_TYPES = {
    "30yr_fixed_mortgage",
    "15yr_fixed_mortgage",
    "5yr_arm_mortgage",
    "savings_1yr_fixed",
    "savings_easy_access",
}

# ISO codes we accept. The seed is USD-only (dirty variants normalized in
# cleaning); anything outside this whitelist is quarantined rather than coerced
# into a wrong 3-letter code.
KNOWN_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "SGD", "HKD"}


class RejectReason:
    """Quarantine reason codes, kept in one place so a typo can't slip into
    RawRateResponse.error unnoticed. The values are stored in the DB and asserted
    in tests; don't change them without a data migration."""

    BLANK_PROVIDER = "blank_provider"
    UNKNOWN_RATE_TYPE = "unknown_rate_type"
    NULL_RATE = "null_rate"
    BAD_RATE_VALUE = "bad_rate_value"
    NON_POSITIVE_RATE = "non_positive_rate"
    OUTLIER_RATE = "outlier_rate"
    MISSING_EFFECTIVE_DATE = "missing_effective_date"
    MISSING_OBSERVED_AT = "missing_observed_at"
    FUTURE_EFFECTIVE_DATE = "future_effective_date"
    UNKNOWN_CURRENCY = "unknown_currency"
    BAD_RESPONSE_ID = "bad_response_id"
    SCRAPE_FAILED = "scrape_failed"

# Display names for the known providers, because str.title() mangles acronyms
# ("HSBC" -> "Hsbc", "PNC Bank" -> "Pnc Bank"). Keyed by slug (lowercased,
# whitespace-collapsed provider name).
PROVIDER_DISPLAY = {
    "hsbc": "HSBC",
    "pnc bank": "PNC Bank",
    "td bank": "TD Bank",
    "us bancorp": "US Bancorp",
    "citibank": "Citibank",
    "chase": "Chase",
    "truist": "Truist",
    "capital one": "Capital One",
    "wells fargo": "Wells Fargo",
    "bank of america": "Bank of America",
}
