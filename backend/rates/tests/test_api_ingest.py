import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from rates.cache import latest_key
from rates.models import Rate
from rates.tests.factories import make_rate
from django.core.cache import cache

pytestmark = pytest.mark.django_db


def _body(**overrides):
    body = {
        "provider": "Chase",
        "rate_type": "5yr_arm_mortgage",
        "rate_value": 6.6,
        "effective_date": "2025-05-15",
        "ingestion_ts": "2025-05-15T19:34:00Z",
        "currency": "USD",
        "raw_response_id": str(uuid.uuid4()),
    }
    body.update(overrides)
    return body


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_requires_token():
    response = APIClient().post("/api/rates/ingest", _body(), format="json")
    assert response.status_code == 401


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_rejects_wrong_token():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer wrong")
    response = client.post("/api/rates/ingest", _body(), format="json")
    assert response.status_code == 401


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_creates_with_token():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    response = client.post("/api/rates/ingest", _body(), format="json")
    assert response.status_code == 201
    assert Rate.objects.count() == 1
    assert response.json()["provider"] == "Chase"


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_is_idempotent_on_response_id():
    rid = str(uuid.uuid4())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    first = client.post("/api/rates/ingest", _body(raw_response_id=rid), format="json")
    second = client.post("/api/rates/ingest", _body(raw_response_id=rid), format="json")
    assert Rate.objects.count() == 1
    assert first.status_code == 201  # created
    assert second.status_code == 200  # idempotent replay, not a new resource


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_malformed_bearer_header_rejected():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer")  # scheme only, no token
    assert client.post("/api/rates/ingest", _body(), format="json").status_code == 401


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_401_body_is_structured_without_fields():
    response = APIClient().post("/api/rates/ingest", _body(), format="json")
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "request_failed"
    assert body["fields"] is None  # auth error carries no field-level errors


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_non_uuid_response_id_is_400_not_500():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    response = client.post("/api/rates/ingest", _body(raw_response_id="not-a-uuid"), format="json")
    assert response.status_code == 400  # structured validation error, never a 500


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_overlong_provider_is_400_not_500():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    response = client.post("/api/rates/ingest", _body(provider="x" * 200), format="json")
    assert response.status_code == 400  # length checked at validation, not a DB overflow 500


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_rejects_invalid_with_structured_error():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    response = client.post("/api/rates/ingest", _body(rate_value=-5), format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["fields"] is not None


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_rejects_unknown_field():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    response = client.post("/api/rates/ingest", _body(surprise="x", admin=True), format="json")
    assert response.status_code == 400  # strict: extra keys are a 400, not silently dropped
    body = response.json()
    assert body["error"] == "validation_error"
    assert "surprise" in (body["fields"] or {}) and "admin" in (body["fields"] or {})


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_idempotent_replay_leaves_cache_warm():
    rid = str(uuid.uuid4())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    client.post("/api/rates/ingest", _body(raw_response_id=rid), format="json")  # created + busts
    APIClient().get("/api/rates/latest?type=5yr_arm_mortgage")  # re-warm the cache
    assert cache.get(latest_key("5yr_arm_mortgage")) is not None

    second = client.post("/api/rates/ingest", _body(raw_response_id=rid), format="json")
    assert second.status_code == 200  # idempotent replay
    # A no-op replay must not bust an already-warm cache.
    assert cache.get(latest_key("5yr_arm_mortgage")) is not None


@override_settings(INGEST_API_TOKEN="secret")
def test_ingest_invalidates_latest_cache():
    make_rate("chase", "5yr_arm_mortgage", "6.0", __import__("datetime").date(2025, 1, 1))
    APIClient().get("/api/rates/latest?type=5yr_arm_mortgage")  # populate cache
    assert cache.get(latest_key("5yr_arm_mortgage")) is not None

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    client.post("/api/rates/ingest", _body(), format="json")

    assert cache.get(latest_key("5yr_arm_mortgage")) is None
