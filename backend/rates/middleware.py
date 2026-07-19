"""Slow-query and request-timing logging.

Wraps every SQL query on the connection; any single query slower than
SLOW_QUERY_SECONDS logs a structured warning. Request duration is logged too.
Timing uses time.perf_counter (monotonic). The wrapper is reusable so the Celery
ingestion worker, which never touches Django middleware, gets the same slow-query
warning as the API.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import connection

log = logging.getLogger("rates.api")


def slow_query_wrapper(label: str, logger: logging.Logger = log):
    """Build a connection.execute_wrapper callable that warns on slow queries.

    label identifies where the query ran: a request path, or ingest:<source>.
    """
    threshold = float(getattr(settings, "SLOW_QUERY_SECONDS", 0.2))

    def wrapper(execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            duration = time.perf_counter() - start
            if duration > threshold:
                logger.warning(
                    "slow_query",
                    extra={
                        "path": label,
                        "duration_ms": round(duration * 1000, 1),
                        "sql_hint": str(sql)[:120],
                    },
                )

    return wrapper


class QueryTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        start = time.perf_counter()
        with connection.execute_wrapper(slow_query_wrapper(path)):
            response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        log.info("request", extra={"path": path, "status": response.status_code,
                                   "duration_ms": duration_ms})
        return response
