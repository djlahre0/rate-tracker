"""Structured error envelope for every API failure.

Both handled DRF exceptions and unexpected ones come back as the same JSON body,
{"error", "detail", "fields"}, so a client never sees a bare 500 or an
inconsistent shape.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

log = logging.getLogger("rates.api")


def structured_exception_handler(exc, context) -> Response:
    response = exception_handler(exc, context)

    if response is not None:
        detail = response.data
        fields = None
        message = "request_failed"
        if isinstance(detail, dict):
            # Only 400s carry field-level validation errors under "fields";
            # auth/permission/404/405 bodies are just a message, not field errors.
            if response.status_code == 400:
                fields = detail
                message = "validation_error"
            detail = _first_message(detail)
        elif isinstance(detail, list):
            # A validation error raised with a string or list detail renders as a
            # top-level list. Keep the 400 contract identical to the dict case so a
            # client branching on "validation_error"/fields doesn't miss it.
            if response.status_code == 400:
                fields = {"non_field_errors": detail}
                message = "validation_error"
            detail = _first_message(detail)
        response.data = {
            "error": message,
            "detail": detail,
            "fields": fields,
        }
        return response

    # Unhandled exception -> log it and return a structured 500 (never a bare stack).
    log.exception("unhandled_exception", extra={"path": _path(context)})
    return Response(
        {"error": "internal_error", "detail": "An unexpected error occurred.", "fields": None},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _first_message(data) -> str:
    if isinstance(data, dict):
        for value in data.values():
            return _first_message(value)
    if isinstance(data, (list, tuple)) and data:
        return _first_message(data[0])
    return str(data)


def _path(context) -> str | None:
    request = context.get("request") if context else None
    return getattr(request, "path", None)
