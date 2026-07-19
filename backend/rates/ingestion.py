"""Ingestion pipeline.

Streams batches from any RateSource, cleans each row, lands every row in
RawRateResponse (idempotent on response_id), promotes the valid ones into Rate
(idempotent on the 1:1 response_id link), and quarantines the rest with a reason
code.

Re-running converges to identical DB state: both bulk inserts use
ignore_conflicts=True on unique keys, so already-seen events are skipped. Because
ignore_conflicts hides how many rows each insert actually wrote, `landed` and
`promoted` are measured as row-count deltas instead of guessed from the input.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from .cleaning import clean_and_validate
from .middleware import slow_query_wrapper
from .models import Provider, Rate, RawRateResponse

log = logging.getLogger("rates.ingest")


def _rejected_by_reason() -> dict[str, int]:
    """Current count of quarantined raw rows grouped by rejection reason code."""
    return {
        row["error"]: row["n"]
        for row in RawRateResponse.objects.filter(status=RawRateResponse.Status.REJECTED)
        .values("error")
        .annotate(n=Count("id"))
    }


@dataclass
class IngestStats:
    landed: int = 0  # new raw rows persisted this run
    promoted: int = 0  # new cleaned rates persisted this run
    rejected: Counter = field(default_factory=Counter)  # reason code -> count

    def as_dict(self) -> dict:
        return {"landed": self.landed, "promoted": self.promoted, "rejected": dict(self.rejected)}


def _resolve_providers(names: dict[str, str]) -> dict[str, Provider]:
    """Return {slug: Provider}, creating any missing providers idempotently."""
    if not names:
        return {}
    existing = {p.slug: p for p in Provider.objects.filter(slug__in=names)}
    missing = [Provider(slug=s, canonical_name=n) for s, n in names.items() if s not in existing]
    if missing:
        Provider.objects.bulk_create(missing, ignore_conflicts=True)
        existing = {p.slug: p for p in Provider.objects.filter(slug__in=names)}
    return existing


def ingest(source, *, batch_size: int = 10_000) -> IngestStats:
    stats = IngestStats()
    today = timezone.localdate()
    log.info("ingest_start", extra={"source": source.name})

    # Count as before/after DB deltas rather than per-batch, since ignore_conflicts
    # hides how many rows each insert actually wrote. This makes a re-run report
    # all-zero and avoids double-counting a rejected response_id seen in two batches.
    raw_before = RawRateResponse.objects.count()
    rate_before = Rate.objects.count()
    rejected_before = _rejected_by_reason()

    # The worker doesn't go through Django middleware, so wire the same >200ms
    # slow-query warning the API gets around the batch loop.
    query_timer = connection.execute_wrapper(slow_query_wrapper(f"ingest:{source.name}", log))
    query_timer.__enter__()
    try:
        _run_batches(source, today, batch_size)
    finally:
        query_timer.__exit__(None, None, None)

    stats.landed = RawRateResponse.objects.count() - raw_before
    stats.promoted = Rate.objects.count() - rate_before
    rejected_after = _rejected_by_reason()
    stats.rejected = Counter(
        {
            code: rejected_after.get(code, 0) - rejected_before.get(code, 0)
            for code in set(rejected_after) | set(rejected_before)
            if rejected_after.get(code, 0) - rejected_before.get(code, 0) > 0
        }
    )
    log.info("ingest_end", extra=stats.as_dict())
    return stats


def _run_batches(source, today, batch_size: int) -> None:
    for batch in source.batches():
        # Dedupe repeated response_ids within the batch (keep first) so one bulk
        # INSERT never carries two rows with the same unique key.
        seen: set[str] = set()
        results = []
        for raw in batch:
            if raw.response_id in seen:
                continue
            seen.add(raw.response_id)
            results.append((raw, clean_and_validate(raw, today)))

        with transaction.atomic():
            raw_objs = [
                RawRateResponse(
                    response_id=raw.response_id,
                    payload=raw.payload,
                    source=source.name,
                    source_url=raw.source_url,
                    status=(
                        RawRateResponse.Status.PARSED
                        if result.is_valid
                        else RawRateResponse.Status.REJECTED
                    ),
                    error=result.error_code,
                )
                for raw, result in results
            ]
            RawRateResponse.objects.bulk_create(
                raw_objs, ignore_conflicts=True, batch_size=batch_size
            )

            valid = [(raw, result) for raw, result in results if result.is_valid]
            providers = _resolve_providers({r.slug: r.canonical_name for _, r in valid})
            rate_objs = [
                Rate(
                    provider=providers[result.slug],
                    rate_type=result.rate_type,
                    rate_value=result.rate_value,
                    currency=result.currency,
                    effective_date=result.effective_date,
                    observed_at=result.observed_at,
                    raw_response_id=raw.response_id,
                )
                for raw, result in valid
            ]
            Rate.objects.bulk_create(rate_objs, ignore_conflicts=True, batch_size=batch_size)


def ingest_single(raw, result) -> tuple[Rate, bool]:
    """Land and promote a single validated row (the ingest webhook path).

    Idempotent: if the response_id was already ingested, returns the existing Rate
    instead of creating a duplicate. Returns (rate, created) so the caller can
    answer 201 (created) vs 200 (replay).
    """
    # This path trusts the caller to have validated the row; guard anyway so a
    # future caller can't land an invalid row as a trusted Rate.
    if not result.is_valid:
        raise ValueError(f"ingest_single called with an invalid row: {result.error_code}")
    with transaction.atomic():
        provider = _resolve_providers({result.slug: result.canonical_name})[result.slug]
        RawRateResponse.objects.get_or_create(
            response_id=raw.response_id,
            defaults={
                "payload": raw.payload,
                "source": "webhook",
                "source_url": raw.source_url,
                "status": RawRateResponse.Status.PARSED,
                "error": None,
            },
        )
        rate, created = Rate.objects.get_or_create(
            raw_response_id=raw.response_id,
            defaults={
                "provider": provider,
                "rate_type": result.rate_type,
                "rate_value": result.rate_value,
                "currency": result.currency,
                "effective_date": result.effective_date,
                "observed_at": result.observed_at,
            },
        )
    return rate, created
