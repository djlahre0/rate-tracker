import logging

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.test import APIClient

from rates.middleware import QueryTimingMiddleware
from rates.models import Provider

pytestmark = pytest.mark.django_db


def test_healthz_is_ok_without_db():
    response = APIClient().get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_slow_query_logs_warning(settings):
    settings.SLOW_QUERY_SECONDS = 0.0  # every query counts as slow

    def get_response(request):
        list(Provider.objects.all())  # a real query inside the wrapper
        return HttpResponse("ok")

    middleware = QueryTimingMiddleware(get_response)

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("rates.api")
    handler = Capture()
    logger.addHandler(handler)
    try:
        middleware(RequestFactory().get("/api/rates/latest"))
    finally:
        logger.removeHandler(handler)

    assert any(r.msg == "slow_query" for r in records)


def test_fast_query_does_not_warn(settings):
    settings.SLOW_QUERY_SECONDS = 10.0  # nothing is that slow

    def get_response(request):
        list(Provider.objects.all())
        return HttpResponse("ok")

    middleware = QueryTimingMiddleware(get_response)

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("rates.api")
    handler = Capture()
    logger.addHandler(handler)
    try:
        middleware(RequestFactory().get("/api/rates/latest"))
    finally:
        logger.removeHandler(handler)

    assert not any(r.msg == "slow_query" for r in records)
