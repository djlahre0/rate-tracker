from pathlib import Path
from unittest.mock import Mock

import pytest

from rates.constants import RejectReason
from rates.ingestion import ingest
from rates.models import Provider, Rate, RawRateResponse
from rates.sources import HttpRateSource, SeedFileSource

pytestmark = pytest.mark.django_db

SEED_FIXTURE = Path(__file__).parent / "fixtures" / "rates_fixture.parquet"


def test_ingest_promotes_valid_and_quarantines_invalid():
    stats = ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))

    assert Rate.objects.count() == stats.promoted == 8
    assert RawRateResponse.objects.count() == stats.landed == 12  # 13 rows, 1 dup id
    rejected = RawRateResponse.objects.filter(status="rejected").count()
    assert rejected == sum(stats.rejected.values()) == 4
    assert stats.rejected["null_rate"] == 1
    assert stats.rejected["non_positive_rate"] == 1
    assert stats.rejected["outlier_rate"] == 1
    assert stats.rejected["future_effective_date"] == 1


def test_ingest_is_idempotent():
    ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))
    rates_after_first = Rate.objects.count()
    raws_after_first = RawRateResponse.objects.count()

    ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))  # run again

    assert Rate.objects.count() == rates_after_first
    assert RawRateResponse.objects.count() == raws_after_first


def test_casing_and_currency_normalized_in_db():
    ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))

    assert Provider.objects.filter(slug="hsbc").count() == 1  # not 3
    assert set(Rate.objects.values_list("currency", flat=True)) <= {"USD"}
    # Providers are only created for valid rows.
    assert not Provider.objects.filter(slug="citibank").exists()  # its only row was rejected


def test_rejected_rows_keep_payload_for_replay():
    ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))
    rejected = RawRateResponse.objects.filter(status="rejected", error="null_rate").first()
    assert rejected is not None
    assert rejected.payload  # raw payload retained


def test_ingest_stats_converge_on_rerun():
    # A second idempotent run must report all-zero (nothing new landed/promoted/rejected).
    ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))
    second = ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))
    assert second.landed == 0
    assert second.promoted == 0
    assert dict(second.rejected) == {}


def test_scrape_failure_is_landed_as_replayable_reject():
    # A timing-out endpoint must not be silently dropped: it lands as a rejected raw
    # (with its payload) so it can be replayed, like the seed path.
    client = Mock()
    client.get.side_effect = TimeoutError("gateway down")
    stats = ingest(HttpRateSource(urls=["https://bad/1"], client=client))

    assert Rate.objects.count() == stats.promoted == 0
    landed = RawRateResponse.objects.get(status="rejected", error=RejectReason.SCRAPE_FAILED)
    assert landed.payload["url"] == "https://bad/1"
    assert stats.rejected[RejectReason.SCRAPE_FAILED] == 1


def test_worker_logs_slow_query(settings):
    # The worker doesn't pass through Django middleware, so it must wire the same
    # >200ms slow-query warning itself. Threshold 0 → every query counts as slow.
    import logging

    settings.SLOW_QUERY_SECONDS = 0.0
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("rates.ingest")
    handler = Capture()
    logger.addHandler(handler)
    try:
        ingest(SeedFileSource(SEED_FIXTURE, batch_size=5))
    finally:
        logger.removeHandler(handler)

    assert any(r.msg == "slow_query" for r in records)


def test_scrape_failure_landing_is_idempotent():
    # The deterministic id means re-scraping the same failure converges (no dup rows).
    def run():
        client = Mock()
        client.get.side_effect = TimeoutError("gateway down")
        return ingest(HttpRateSource(urls=["https://bad/1"], client=client))

    run()
    n_after_first = RawRateResponse.objects.count()
    second = run()
    assert RawRateResponse.objects.count() == n_after_first
    assert second.landed == 0
