from pathlib import Path

import pytest
from django.core.management import call_command

from rates.models import Rate

pytestmark = pytest.mark.django_db

SEED_FIXTURE = Path(__file__).parent / "fixtures" / "rates_fixture.parquet"


def test_seed_data_command_loads_fixture():
    call_command("seed_data", path=str(SEED_FIXTURE), batch_size=5)
    assert Rate.objects.count() == 8


def test_seed_data_command_is_idempotent():
    call_command("seed_data", path=str(SEED_FIXTURE), batch_size=5)
    call_command("seed_data", path=str(SEED_FIXTURE), batch_size=5)
    assert Rate.objects.count() == 8


def test_seed_data_command_since_limits_to_recent_rows():
    call_command("seed_data", path=str(SEED_FIXTURE), batch_size=5, since="2025-10-01")
    # Only the recent, valid rows are promoted — fewer than the full-load 8.
    assert 0 < Rate.objects.count() < 8


def test_seed_data_command_days_large_window_loads_all():
    call_command("seed_data", path=str(SEED_FIXTURE), batch_size=5, days=100_000)
    assert Rate.objects.count() == 8
