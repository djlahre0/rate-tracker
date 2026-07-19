"""Query helpers backing the API endpoints.

Kept separate from views so the DB access patterns (and the indexes that serve
them) are readable in one place.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db import connection
from django.db.models import QuerySet

from .models import Rate

# The comparison table's sparkline + "30-day change" chip read the most recent
# N distinct dates that have data per series — data-anchored, not a calendar
# window, so it matches the chart and survives the seed's sparse recent tail.
SUMMARY_SPARK_POINTS = 30


def latest_rates(rate_type: str | None = None) -> QuerySet[Rate]:
    """Most recent rate per (provider, rate_type).

    Served by rate_latest_idx. Postgres DISTINCT ON picks the newest row per group;
    the ORDER BY has to lead with the DISTINCT ON columns.
    """
    qs = Rate.objects.select_related("provider")
    if rate_type:
        qs = qs.filter(rate_type=rate_type)
    return qs.order_by(
        "provider_id", "rate_type", "-effective_date", "-observed_at"
    ).distinct("provider_id", "rate_type")


def history(
    provider_slug: str, rate_type: str, date_from: dt.date, date_to: dt.date
) -> QuerySet[Rate]:
    """Raw time-series for one provider + type within a bounded date window."""
    return (
        Rate.objects.select_related("provider")
        .filter(
            provider__slug=provider_slug,
            rate_type=rate_type,
            effective_date__gte=date_from,
            effective_date__lte=date_to,
        )
        .order_by("effective_date", "observed_at")
    )


def history_daily(
    provider_slug: str, rate_type: str, date_from: dt.date, date_to: dt.date
) -> QuerySet[Rate]:
    """One point per day: the latest observation of each effective_date.

    The seed carries many intraday readings per day, so reducing to one keeps the
    chart line clean. DISTINCT ON (effective_date), taking the latest observed_at
    per day, served by rate_latest_idx.
    """
    return (
        Rate.objects.select_related("provider")
        .filter(
            provider__slug=provider_slug,
            rate_type=rate_type,
            effective_date__gte=date_from,
            effective_date__lte=date_to,
        )
        # -id is a final tiebreaker so two readings that share the same observed_at
        # on a day resolve deterministically.
        .order_by("effective_date", "-observed_at", "-id")
        .distinct("effective_date")
    )


def default_history_window(
    provider_slug: str, rate_type: str, days: int
) -> tuple[dt.date, dt.date]:
    """Window covering the most recent `days` distinct dates that have data.

    Rate data is gappy (missing days, sparse tails), so a plain calendar window
    ending today can come back nearly empty. Anchoring to the last N dates that
    actually have data keeps the chart full. Falls back to a calendar window ending
    today when the series has no data at all.
    """
    from django.utils import timezone

    dates = list(
        Rate.objects.filter(provider__slug=provider_slug, rate_type=rate_type)
        .order_by("-effective_date")
        .values_list("effective_date", flat=True)
        .distinct()[:days]
    )
    if not dates:
        today = timezone.localdate()
        return today - dt.timedelta(days=days), today
    return dates[-1], dates[0]  # (oldest-of-the-N-most-recent, newest)


def _summary_points(rate_type: str | None) -> dict[tuple[int, str], list[Decimal]]:
    """Per series → its most recent ≤N daily values, oldest → newest.

    One window-function query for every series at once (no per-series N+1). The
    `daily` CTE collapses each (provider, rate_type, effective_date) to its latest
    observation (same rule as history_daily); the window ranks those days newest
    first per series and keeps the top N. Anchoring to the last N dates that
    actually have data — rather than a calendar window — is what makes the
    sparkline match the chart on the seed's gappy, sparse-recent data.
    """
    table = Rate._meta.db_table
    where = "WHERE rate_type = %s" if rate_type else ""
    params: list = [rate_type] if rate_type else []
    params.append(SUMMARY_SPARK_POINTS)

    sql = f"""
        WITH daily AS (
            SELECT DISTINCT ON (provider_id, rate_type, effective_date)
                   provider_id, rate_type, effective_date, rate_value
            FROM {table}
            {where}
            ORDER BY provider_id, rate_type, effective_date DESC, observed_at DESC, id DESC
        ),
        ranked AS (
            SELECT provider_id, rate_type, effective_date, rate_value,
                   ROW_NUMBER() OVER (
                       PARTITION BY provider_id, rate_type ORDER BY effective_date DESC
                   ) AS rn
            FROM daily
        )
        SELECT provider_id, rate_type, rate_value
        FROM ranked
        WHERE rn <= %s
        ORDER BY provider_id, rate_type, effective_date ASC
    """

    series: dict[tuple[int, str], list[Decimal]] = defaultdict(list)
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for provider_id, rt, value in cursor.fetchall():
            series[(provider_id, rt)].append(value)
    return series


def rate_summary(rate_type: str | None = None) -> list[dict]:
    """Latest rate per series plus its sparkline and change. Backs /rates/summary.

    Combines the authoritative current value per series (latest_rates) with the
    last SUMMARY_SPARK_POINTS daily values (_summary_points). `change_30d` is the
    last − first of that sparkline, so the chip and the drawn line always agree;
    a series with fewer than two points reports a null change but still shows its
    current value.
    """
    series = _summary_points(rate_type)

    rows: list[dict] = []
    for head in latest_rates(rate_type):
        values = series.get((head.provider_id, head.rate_type), [])  # oldest → newest
        spark = [float(v) for v in values]

        change: Decimal | None = None
        change_pct: float | None = None
        if len(values) >= 2:
            change = values[-1] - values[0]
            if values[0] != 0:
                change_pct = float(change / values[0] * 100)

        rows.append(
            {
                "provider": head.provider.canonical_name,
                "provider_slug": head.provider.slug,
                "rate_type": head.rate_type,
                "currency": head.currency,
                "rate_value": head.rate_value,
                "effective_date": head.effective_date,
                "ingested_at": head.ingested_at,
                "change_30d": change,
                "change_30d_pct": change_pct,
                "spark": spark,
            }
        )
    return rows
