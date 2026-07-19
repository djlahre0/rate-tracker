"""Bounded pagination so /rates/history never returns an unbounded result set."""

from rest_framework.pagination import LimitOffsetPagination


class BoundedLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 500
