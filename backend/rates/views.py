"""API views.

- GET  /api/rates/latest   latest per (provider, type); Redis-cached.
- GET  /api/rates/summary  latest + 30-day change + sparkline per series; Redis-cached.
- GET  /api/rates/history  bounded, paginated time-series.
- POST /api/rates/ingest   bearer-authed webhook; strict validation.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import queries
from .authentication import BearerTokenAuthentication
from .cache import (
    LATEST_TTL_SECONDS,
    SUMMARY_TTL_SECONDS,
    invalidate_latest,
    latest_key,
    summary_key,
)
from .constants import RATE_TYPES
from .models import Provider
from .pagination import BoundedLimitOffsetPagination
from .serializers import IngestSerializer, RateSerializer, SummarySerializer

from django.core.cache import cache

DEFAULT_HISTORY_WINDOW_DAYS = 30
MAX_HISTORY_WINDOW_DAYS = 366
VALID_GRANULARITIES = {"raw", "daily"}


class HealthzView(APIView):
    """Cheap liveness probe (no DB/cache hit) for the container healthcheck."""

    def get(self, request):
        return Response({"status": "ok"})


class LatestRatesView(APIView):
    """Most recent rate per provider, optionally filtered by ?type=. Cached."""

    def get(self, request):
        rate_type = request.query_params.get("type")
        if rate_type and rate_type not in RATE_TYPES:
            raise ValidationError({"type": f"Unknown rate type '{rate_type}'."})

        key = latest_key(rate_type)
        payload = cache.get(key)
        if payload is None:
            rows = queries.latest_rates(rate_type)
            # Cache plain dicts rather than the DRF ReturnList, which drags the bound
            # serializer and queryset graph into the pickle.
            payload = [dict(row) for row in RateSerializer(rows, many=True).data]
            cache.set(key, payload, LATEST_TTL_SECONDS)
        return Response(payload)


class SummaryView(APIView):
    """Comparison view: latest rate + 30-day change + sparkline per series. Cached.

    Same cache + ?type= contract as LatestRatesView, under the rates:summary:
    namespace. One extra bounded query beyond /latest builds the per-series
    sparkline and change, so the dashboard's table and KPI strip come from a
    single request instead of one /history call per row.
    """

    def get(self, request):
        rate_type = request.query_params.get("type")
        if rate_type and rate_type not in RATE_TYPES:
            raise ValidationError({"type": f"Unknown rate type '{rate_type}'."})

        key = summary_key(rate_type)
        payload = cache.get(key)
        if payload is None:
            rows = queries.rate_summary(rate_type)
            # Cache plain dicts, not the DRF ReturnList (see LatestRatesView).
            payload = [dict(row) for row in SummarySerializer(rows, many=True).data]
            cache.set(key, payload, SUMMARY_TTL_SECONDS)
        return Response(payload)


class HistoryView(ListAPIView):
    """Paginated, bounded time-series for one provider + type."""

    serializer_class = RateSerializer
    pagination_class = BoundedLimitOffsetPagination

    def get_queryset(self):
        params = self.request.query_params
        provider = params.get("provider")
        rate_type = params.get("type")
        if not provider or not rate_type:
            raise ValidationError(
                {"detail": "Both 'provider' and 'type' query parameters are required."}
            )
        if rate_type not in RATE_TYPES:
            raise ValidationError({"type": f"Unknown rate type '{rate_type}'."})

        granularity = params.get("granularity", "raw")
        if granularity not in VALID_GRANULARITIES:
            raise ValidationError({"granularity": "Must be 'daily' or 'raw'."})

        explicit_from = _parse_date(params.get("from"))
        explicit_to = _parse_date(params.get("to"))
        if explicit_from is None and explicit_to is None:
            # No window given → the most recent 30 days that actually have data.
            date_from, date_to = queries.default_history_window(
                provider, rate_type, DEFAULT_HISTORY_WINDOW_DAYS
            )
        else:
            date_to = explicit_to or timezone.localdate()
            date_from = explicit_from or (date_to - dt.timedelta(days=DEFAULT_HISTORY_WINDOW_DAYS))
            if date_from > date_to:
                raise ValidationError({"detail": "'from' must be on or before 'to'."})
            if (date_to - date_from).days > MAX_HISTORY_WINDOW_DAYS:
                if explicit_to is None:
                    # `to` defaulted to today → clamp to the most recent max-window
                    # slice rather than rejecting an open-ended "since <date>" query.
                    date_from = date_to - dt.timedelta(days=MAX_HISTORY_WINDOW_DAYS)
                else:
                    raise ValidationError(
                        {"detail": f"Date window cannot exceed {MAX_HISTORY_WINDOW_DAYS} days."}
                    )

        # The request is well-formed; an unknown provider slug would return an empty
        # page indistinguishable from "no data in window", so make it a 404 instead.
        if not Provider.objects.filter(slug=provider).exists():
            raise NotFound(f"No provider with slug '{provider}'.")

        if granularity == "daily":
            return queries.history_daily(provider, rate_type, date_from, date_to)
        return queries.history(provider, rate_type, date_from, date_to)


class IngestView(APIView):
    """Authenticated webhook: validate strictly, write, invalidate cache."""

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rate = serializer.save()
        # Only a real write changes /rates/latest, so skip the cache bust on a
        # replay where get_or_create created nothing.
        if serializer.was_created:
            invalidate_latest()
        # 201 for a new rate, 200 when an already-seen response_id is replayed.
        code = status.HTTP_201_CREATED if serializer.was_created else status.HTTP_200_OK
        return Response(RateSerializer(rate).data, status=code)


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({"detail": f"Invalid date '{value}', expected YYYY-MM-DD."}) from exc
