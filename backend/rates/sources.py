"""Rate sources: one interface, two implementations.

A RateSource yields batches of RawRate. SeedFileSource streams the parquet with
pyarrow so memory stays bounded; HttpRateSource scrapes JSON endpoints and keeps
going through timeouts, HTTP errors, and partial responses instead of crashing.
Either way every row is landed for replay: a failed scrape or an unparseable id
carries a reject_reason rather than being dropped.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from pathlib import Path
from typing import Iterator, Protocol

import httpx
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from .cleaning import RawRate
from .constants import RejectReason

log = logging.getLogger("rates.ingest")


def _to_date(value: object) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _to_dt(value: object) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:  # parquet timestamps are naive UTC
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _coerce_response_id(value: object, payload: dict) -> tuple[str, bool]:
    """Return (uuid_str, is_bad).

    response_id is both the idempotency key and a UUIDField, so a missing or
    malformed id can't be stored as-is (str(None) == "None" would collapse rows
    onto one key). For a bad id we hash the payload into a deterministic uuid5, so
    re-runs converge and distinct rows stay distinct, and flag it so cleaning
    quarantines the row as bad_response_id.
    """
    text = "" if value is None else str(value)
    try:
        return str(uuid.UUID(text)), False
    except (ValueError, AttributeError, TypeError):
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical)), True


class RateSource(Protocol):
    name: str

    def batches(self) -> Iterator[list[RawRate]]: ...


class SeedFileSource:
    """Streams the seed parquet in row-group-sized batches. Codec is auto-detected.

    An optional `since` bounds the read to rows with effective_date >= since,
    pushed down to pyarrow so unmatched row groups are skipped rather than read
    and discarded. Used to seed a bounded, representative slice on a free-tier
    deploy while local runs load the full history.
    """

    name = "seed"

    def __init__(
        self, path: str | Path, batch_size: int = 50_000, since: dt.date | None = None
    ):
        self.path = Path(path)
        self.batch_size = batch_size
        self.since = since

    def _record_batches(self):
        if self.since is None:
            yield from pq.ParquetFile(self.path).iter_batches(batch_size=self.batch_size)
            return
        # Predicate pushdown on effective_date; row groups outside the window are skipped.
        scanner = ds.dataset(self.path, format="parquet").scanner(
            filter=ds.field("effective_date") >= self.since,
            batch_size=self.batch_size,
        )
        yield from scanner.to_batches()

    def batches(self) -> Iterator[list[RawRate]]:
        for record_batch in self._record_batches():
            rows = record_batch.to_pylist()
            batch = []
            for row in rows:
                response_id, bad_id = _coerce_response_id(row.get("raw_response_id"), row)
                batch.append(
                    RawRate(
                        provider=row.get("provider"),
                        rate_type=row.get("rate_type"),
                        rate_value=row.get("rate_value"),
                        effective_date=_to_date(row.get("effective_date")),
                        observed_at=_to_dt(row.get("ingestion_ts")),
                        source_url=row.get("source_url"),
                        response_id=response_id,
                        currency=row.get("currency"),
                        payload=row,
                        reject_reason=RejectReason.BAD_RESPONSE_ID if bad_id else None,
                    )
                )
            yield batch


class HttpRateSource:
    """Scrapes provider JSON endpoints, one reading per URL.

    A failed URL (timeout, HTTP error, or unparseable body) is logged and emitted
    as a quarantined RawRate with a reject_reason, so ingestion still lands it in
    raw_rate_response for replay. A partial scrape returns the readings that did
    succeed.
    """

    name = "scraper"

    def __init__(self, urls: list[str], client=None, timeout: float = 10.0):
        self.urls = urls
        self.timeout = timeout
        self._owns_client = client is None
        self.client = client if client is not None else httpx.Client(timeout=timeout)

    def parse(self, payload: dict, url: str) -> RawRate:
        response_id, bad_id = _coerce_response_id(payload.get("raw_response_id"), payload)
        return RawRate(
            provider=payload["provider"],
            rate_type=payload["rate_type"],
            rate_value=payload.get("rate_value"),
            effective_date=_to_date(payload["effective_date"]),
            observed_at=_to_dt(payload["ingestion_ts"]),
            source_url=url,
            response_id=response_id,
            currency=payload.get("currency"),
            payload=payload,
            reject_reason=RejectReason.BAD_RESPONSE_ID if bad_id else None,
        )

    def _failed_row(self, url: str, exc: Exception) -> RawRate:
        payload = {"url": url, "error": str(exc)}
        # Deterministic id from url+error so repeated identical failures converge.
        response_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"scrape_failed:{url}:{exc}"))
        return RawRate(
            provider=None,
            rate_type=None,
            rate_value=None,
            effective_date=None,
            observed_at=None,
            source_url=url,
            response_id=response_id,
            currency=None,
            payload=payload,
            reject_reason=RejectReason.SCRAPE_FAILED,
        )

    def batches(self) -> Iterator[list[RawRate]]:
        rows: list[RawRate] = []
        try:
            for url in self.urls:
                try:
                    response = self.client.get(url)
                    response.raise_for_status()
                    rows.append(self.parse(response.json(), url))
                # Land expected transport/parse failures for replay; a real bug
                # (anything outside these types) still propagates.
                except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
                    log.warning("scrape_failed", extra={"url": url, "error": str(exc)})
                    rows.append(self._failed_row(url, exc))
        finally:
            if self._owns_client:
                self.client.close()
        yield rows
