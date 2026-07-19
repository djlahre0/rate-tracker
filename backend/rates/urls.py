from django.urls import path

from .views import (
    HealthzView,
    HistoryView,
    IngestView,
    LatestRatesView,
    SummaryView,
)

urlpatterns = [
    path("healthz", HealthzView.as_view(), name="healthz"),
    path("rates/latest", LatestRatesView.as_view(), name="rates-latest"),
    path("rates/summary", SummaryView.as_view(), name="rates-summary"),
    path("rates/history", HistoryView.as_view(), name="rates-history"),
    path("rates/ingest", IngestView.as_view(), name="rates-ingest"),
]
