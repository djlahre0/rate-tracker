"""DRF serializers for read responses and the ingest webhook."""

from __future__ import annotations

import datetime as dt
import uuid

from django.utils import timezone
from rest_framework import serializers

from .cleaning import RawRate, clean_and_validate
from .constants import RATE_TYPES
from .ingestion import ingest_single


class RateSerializer(serializers.Serializer):
    """Read shape for latest + history responses."""

    provider = serializers.CharField(source="provider.canonical_name")
    provider_slug = serializers.CharField(source="provider.slug")
    rate_type = serializers.CharField()
    rate_value = serializers.DecimalField(max_digits=6, decimal_places=4)
    currency = serializers.CharField()
    effective_date = serializers.DateField()
    observed_at = serializers.DateTimeField()
    ingested_at = serializers.DateTimeField()


class SummarySerializer(serializers.Serializer):
    """Read shape for the /rates/summary comparison view.

    Extends the latest-rate fields with a ~30-day sparkline and change. Serializes
    plain dicts produced by queries.rate_summary (not model instances), so every
    field reads its value by name. change_30d/change_30d_pct are null when the
    window has too few points to compare.
    """

    provider = serializers.CharField()
    provider_slug = serializers.CharField()
    rate_type = serializers.CharField()
    currency = serializers.CharField()
    rate_value = serializers.DecimalField(max_digits=6, decimal_places=4)
    effective_date = serializers.DateField()
    ingested_at = serializers.DateTimeField()
    change_30d = serializers.DecimalField(
        max_digits=7, decimal_places=4, allow_null=True
    )
    change_30d_pct = serializers.FloatField(allow_null=True)
    spark = serializers.ListField(child=serializers.FloatField())


class IngestSerializer(serializers.Serializer):
    """Strict input validation for POST /rates/ingest.

    Reuses clean_and_validate so the webhook enforces the same rules as bulk
    ingestion. An invalid row raises a ValidationError keyed by the reason code,
    which the client sees as a structured 400 rather than a 500.
    """

    # max_length matches Provider.slug (100) so an overlong value is a 400 rather
    # than a DB-overflow 500; raw_response_id as a UUIDField makes a non-UUID a 400.
    provider = serializers.CharField(max_length=100)
    rate_type = serializers.ChoiceField(choices=sorted(RATE_TYPES))
    rate_value = serializers.FloatField()
    effective_date = serializers.DateField()
    ingestion_ts = serializers.DateTimeField()
    currency = serializers.CharField(required=False, default="USD", max_length=32)
    source_url = serializers.CharField(
        required=False, allow_null=True, default=None, max_length=500
    )
    raw_response_id = serializers.UUIDField(required=False)

    def validate(self, attrs: dict) -> dict:
        # Reject any field the client sent that we don't declare, so a typo'd or
        # spurious key is a 400 instead of being silently dropped (DRF's default).
        if isinstance(self.initial_data, dict):
            unknown = set(self.initial_data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {name: "Unexpected field." for name in sorted(unknown)}
                )

        response_id = str(attrs.get("raw_response_id") or uuid.uuid4())
        raw = RawRate(
            provider=attrs["provider"],
            rate_type=attrs["rate_type"],
            rate_value=attrs["rate_value"],
            effective_date=attrs["effective_date"],
            observed_at=attrs["ingestion_ts"],
            source_url=attrs.get("source_url"),
            response_id=response_id,
            currency=attrs.get("currency"),
            payload={k: _json_safe(v) for k, v in attrs.items()},
        )
        result = clean_and_validate(raw, timezone.localdate())
        if not result.is_valid:
            raise serializers.ValidationError({result.error_code: "rejected by cleaning rules"})
        attrs["_raw"] = raw
        attrs["_result"] = result
        return attrs

    def create(self, validated_data: dict):
        rate, self.was_created = ingest_single(
            validated_data["_raw"], validated_data["_result"]
        )
        return rate


def _json_safe(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
