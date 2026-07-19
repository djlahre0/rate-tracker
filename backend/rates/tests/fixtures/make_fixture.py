"""Generate a tiny fixture parquet that embeds every seed-file data issue.

Run once to (re)create ``rates_fixture.parquet``:

    python rates/tests/fixtures/make_fixture.py

Schema mirrors the real seed (effective_date as date32, ingestion_ts as
timestamp[us]). Expected ingestion outcome (see test_ingestion.py):
  * 13 rows, 12 distinct response_ids (one duplicated, both valid)
  * landed = 12, promoted = 8
  * rejected = {null_rate:1, non_positive_rate:1, outlier_rate:1, future_effective_date:1}
  * provider 'hsbc' appears once despite HSBC/Hsbc/hsbc casing
"""

import datetime as dt
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def rid(n: int) -> str:
    """Deterministic, valid UUID string (the real seed keys on UUIDs)."""
    return str(uuid.UUID(int=n))


DUP_ID = rid(5)  # shared by two valid Chase rows

# (provider, rate_type, rate_value, effective_date, currency, response_id)
ROWS = [
    ("HSBC", "savings_1yr_fixed", 4.7647, dt.date(2025, 1, 12), "USD", rid(1)),
    ("Hsbc", "savings_easy_access", 5.3826, dt.date(2025, 6, 22), "US Dollar", rid(2)),
    ("hsbc", "5yr_arm_mortgage", 5.9810, dt.date(2025, 3, 24), "usd", rid(3)),
    ("Chase", "5yr_arm_mortgage", 6.6080, dt.date(2025, 5, 15), "USD", rid(4)),
    ("Chase", "5yr_arm_mortgage", 7.2163, dt.date(2025, 10, 3), "USD", DUP_ID),
    ("Truist", "savings_1yr_fixed", None, dt.date(2026, 2, 25), "USD", rid(6)),         # null_rate
    ("Citibank", "30yr_fixed_mortgage", -1.8440, dt.date(2025, 4, 30), "USD", rid(7)),  # non_positive
    ("PNC Bank", "15yr_fixed_mortgage", 97.4000, dt.date(2025, 7, 1), "USD", rid(8)),   # outlier
    ("Wells Fargo", "30yr_fixed_mortgage", 6.5, dt.date(2099, 1, 1), "USD", rid(9)),    # future
    ("Capital One", "savings_easy_access", 4.3236, dt.date(2025, 4, 30), "USD", rid(10)),
    ("TD Bank", "15yr_fixed_mortgage", 6.7018, dt.date(2024, 10, 8), "USD", rid(11)),
    ("US Bancorp", "savings_1yr_fixed", 5.4394, dt.date(2025, 10, 19), "USD", rid(12)),
    ("Chase", "5yr_arm_mortgage", 7.2163, dt.date(2025, 10, 3), "USD", DUP_ID),         # duplicate id
]


def build_table() -> pa.Table:
    def ts(d: dt.date) -> dt.datetime:
        return dt.datetime(d.year, d.month, d.day, 12, 0, 0)

    columns = {
        "provider": pa.array([r[0] for r in ROWS], pa.string()),
        "rate_type": pa.array([r[1] for r in ROWS], pa.string()),
        "rate_value": pa.array([r[2] for r in ROWS], pa.float64()),
        "effective_date": pa.array([r[3] for r in ROWS], pa.date32()),
        "ingestion_ts": pa.array([ts(r[3]) for r in ROWS], pa.timestamp("us")),
        "source_url": pa.array(
            [f"https://www.{r[0].strip().lower().replace(' ', '-')}.com/rates/{r[1]}" for r in ROWS],
            pa.string(),
        ),
        "raw_response_id": pa.array([r[5] for r in ROWS], pa.string()),
        "currency": pa.array([r[4] for r in ROWS], pa.string()),
    }
    return pa.table(columns)


if __name__ == "__main__":
    out = Path(__file__).parent / "rates_fixture.parquet"
    pq.write_table(build_table(), out, compression="zstd")
    print(f"wrote {out} ({len(ROWS)} rows)")
