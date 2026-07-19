import datetime as dt
import json
from pathlib import Path
from unittest.mock import Mock

from rates.constants import RejectReason
from rates.sources import HttpRateSource, SeedFileSource

FIXTURES = Path(__file__).parent / "fixtures"
HTTP_FIXTURE = FIXTURES / "http_rate_response.json"
SEED_FIXTURE = FIXTURES / "rates_fixture.parquet"


def test_http_source_parses_mocked_response_to_expected_rawrate():
    """Mock the HTTP call and assert the parsed row matches the fixture."""
    payload = json.loads(HTTP_FIXTURE.read_text())
    client = Mock()
    client.get.return_value = Mock(
        status_code=200, json=lambda: payload, raise_for_status=lambda: None
    )
    source = HttpRateSource(
        urls=["https://www.hsbc.com/rates/savings_1yr_fixed"], client=client
    )

    rows = [row for batch in source.batches() for row in batch]

    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "HSBC"
    assert row.rate_type == "savings_1yr_fixed"
    assert row.rate_value == 4.7647
    assert row.currency == "USD"
    assert row.response_id == "8868d928-f83a-4088-980e-0b55fcba21ec"
    assert row.effective_date == dt.date(2025, 1, 12)
    assert row.observed_at == dt.datetime(2025, 1, 12, 22, 34, 5, tzinfo=dt.timezone.utc)


def test_http_source_survives_timeout_and_lands_failure_for_replay():
    client = Mock()
    client.get.side_effect = TimeoutError("slow endpoint")
    source = HttpRateSource(urls=["https://example/x"], client=client)

    rows = [row for batch in source.batches() for row in batch]

    # No exception, and the failure is LANDED (not dropped) so it can be replayed.
    assert len(rows) == 1
    assert rows[0].reject_reason == RejectReason.SCRAPE_FAILED
    assert rows[0].payload["url"] == "https://example/x"
    assert "slow endpoint" in rows[0].payload["error"]


def test_http_source_partial_failure_returns_successes_and_lands_failures():
    payload = json.loads(HTTP_FIXTURE.read_text())
    ok = Mock(status_code=200, json=lambda: payload, raise_for_status=lambda: None)
    client = Mock()
    client.get.side_effect = [TimeoutError("boom"), ok]
    source = HttpRateSource(urls=["https://bad/1", "https://good/2"], client=client)

    rows = [row for batch in source.batches() for row in batch]

    assert len(rows) == 2
    good = [r for r in rows if r.reject_reason is None]
    failed = [r for r in rows if r.reject_reason == RejectReason.SCRAPE_FAILED]
    assert len(good) == 1 and good[0].provider == "HSBC"
    assert len(failed) == 1 and failed[0].source_url == "https://bad/1"


def test_seed_source_streams_rawrates_from_parquet():
    source = SeedFileSource(SEED_FIXTURE, batch_size=5)
    batches = list(source.batches())
    rows = [row for batch in batches for row in batch]

    assert len(batches) == 3  # 13 rows in batches of 5, 5, 3
    assert len(rows) == 13
    assert rows[0].provider == "HSBC"
    assert rows[0].observed_at.tzinfo is not None  # naive parquet ts made UTC-aware


def test_seed_source_since_bounds_to_recent_effective_dates():
    since = dt.date(2025, 10, 1)
    bounded = [r for b in SeedFileSource(SEED_FIXTURE, batch_size=5, since=since).batches() for r in b]
    full = [r for b in SeedFileSource(SEED_FIXTURE, batch_size=5).batches() for r in b]

    assert 0 < len(bounded) < len(full)
    assert all(r.effective_date >= since for r in bounded)


def test_seed_source_since_after_all_dates_yields_nothing():
    rows = [r for b in SeedFileSource(SEED_FIXTURE, since=dt.date(2100, 1, 1)).batches() for r in b]
    assert rows == []
