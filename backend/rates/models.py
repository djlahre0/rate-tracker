"""Data model.

Three tables that separate what we received from what we trust:

- Provider         canonical dimension; fixes provider-name casing once.
- RawRateResponse  landing zone; every source row verbatim, keyed by a unique
                   response_id. The idempotency anchor and the replay store for
                   rejected rows.
- Rate             the cleaned fact; one row per valid observation, linked 1:1
                   back to its raw response.
"""

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .constants import RATE_TYPES


class Provider(models.Model):
    """A rate provider. slug is the normalized identity (casing collapsed)."""

    slug = models.CharField(max_length=100, unique=True)
    canonical_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.canonical_name


class RawRateResponse(models.Model):
    """Raw landing record, stored before cleaning so failed parses can be replayed."""

    class Status(models.TextChoices):
        PARSED = "parsed", "Parsed"
        REJECTED = "rejected", "Rejected"

    # Source event id (parquet raw_response_id); webhook posts generate one.
    response_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # DjangoJSONEncoder so raw date/datetime/Decimal values serialize cleanly.
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    source = models.CharField(max_length=20)  # seed | scraper | webhook
    source_url = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.TextField(null=True, blank=True)  # rejection reason code, if any
    received_at = models.DateTimeField(auto_now_add=True)  # when we received it

    class Meta:
        indexes = [models.Index(fields=["status"], name="raw_status_idx")]

    def __str__(self) -> str:
        return f"{self.response_id} ({self.status})"


class Rate(models.Model):
    """A cleaned, validated rate observation."""

    RATE_TYPE_CHOICES = [(t, t) for t in sorted(RATE_TYPES)]

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name="rates")
    rate_type = models.CharField(max_length=50, choices=RATE_TYPE_CHOICES)
    rate_value = models.DecimalField(max_digits=6, decimal_places=4)
    currency = models.CharField(max_length=3)
    effective_date = models.DateField()
    observed_at = models.DateTimeField()  # source ingestion_ts (when published)
    ingested_at = models.DateTimeField(auto_now_add=True)  # our ingest time
    raw_response = models.OneToOneField(
        RawRateResponse,
        on_delete=models.CASCADE,
        to_field="response_id",
        db_column="raw_response_id",
        related_name="rate",
    )

    class Meta:
        indexes = [
            # Latest rate per provider (+ optional type) via DISTINCT ON.
            models.Index(
                fields=["provider", "rate_type", "-effective_date", "-observed_at"],
                name="rate_latest_idx",
            ),
            # 30-day change for a given type across providers.
            models.Index(fields=["rate_type", "-effective_date"], name="rate_type_date_idx"),
            # All records ingested in a 24-hour window.
            models.Index(fields=["ingested_at"], name="rate_ingested_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider.slug} {self.rate_type} {self.rate_value} @ {self.effective_date}"
