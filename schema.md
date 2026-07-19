# schema.md: database design

PostgreSQL 18. Three tables that separate what we received (raw landing) from what we
trust (cleaned fact), with a small provider dimension to fix casing once. All schema
is defined in Django migrations (`backend/rates/migrations/`), not raw SQL dumps.

```
 provider (dimension)          raw_rate_response (landing)          rate (cleaned fact)
 ┌──────────────────┐          ┌───────────────────────────┐       ┌──────────────────────┐
 │ id  (PK)         │◄────┐    │ id (PK)                   │       │ id (PK)              │
 │ slug (unique)    │     │    │ response_id (UUID, unique)│◄──────│ raw_response (1:1)   │
 │ canonical_name   │     └────│ ...                       │  to    │ provider (FK) ───────┼──┐
 │ created_at       │          │ payload (JSONB)           │response │ rate_type            │  │
 └──────────────────┘          │ source / source_url       │  _id   │ rate_value NUMERIC   │  │
                               │ status / error            │       │ currency             │  │
                               │ received_at               │       │ effective_date       │  │
                               └───────────────────────────┘       │ observed_at          │  │
                                                                    │ ingested_at          │  │
                                                                    └──────────────────────┘  │
                                          provider.id ◄─────────────────────────────────────────┘
```

---

## Tables

### `provider` (dimension)
Canonicalizes provider identity so the `HSBC` / `Hsbc` / `hsbc` casing problem is
solved once at ingest, not re-normalized in every query.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `slug` | varchar **unique** | normalized identity (`strip().lower()`, whitespace-collapsed) |
| `canonical_name` | varchar | display name; acronym-aware map for the known providers |
| `created_at` | timestamptz | |

**Index:** unique on `slug` (identity lookups + dedupe on ingest).

### `raw_rate_response` (landing / provenance / replay)
Every source row, verbatim, before cleaning. This is the idempotency anchor and the
replay store for quarantined rows.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `response_id` | uuid **unique** | source `raw_response_id`; the idempotency key |
| `payload` | jsonb | the raw row as received (uncleaned) |
| `source` | varchar | `seed` \| `scraper` \| `webhook` |
| `source_url` | text | |
| `status` | varchar | `parsed` \| `rejected` |
| `error` | text | rejection reason code (e.g. `outlier_rate`) |
| `received_at` | timestamptz | when we received it |

**Indexes:** unique on `response_id` (idempotent landing); btree on `status`
(operators querying quarantined rows).

### `rate` (cleaned fact)
One row per **valid** observation. Invalid rows never reach this table.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `provider_id` | bigint FK → `provider` (PROTECT) | |
| `rate_type` | varchar (5 choices) | |
| `rate_value` | **numeric(6,4)** | exact decimal, not float |
| `currency` | varchar(3) | normalized ISO |
| `effective_date` | date | the rate's effective date |
| `observed_at` | timestamptz | source `ingestion_ts` (when published) |
| `ingested_at` | timestamptz | **our** ingest time |
| `raw_response_id` | uuid **unique** (1:1 → `raw_rate_response.response_id`) | provenance + fact-level idempotency |

Why `numeric` not `float`: rates are money-adjacent; float rounding is unacceptable.
Why two timestamps: the brief's "ingestion timestamp" is ours (`ingested_at`); the
source's own timestamp is kept as `observed_at` and is what "latest" tie-breaks on.

---

## The three required queries and the indexes that serve them

Indexes on `rate`:

```python
Index(fields=["provider", "rate_type", "-effective_date", "-observed_at"])  # rate_latest_idx
Index(fields=["rate_type", "-effective_date"])                              # rate_type_date_idx
Index(fields=["ingested_at"])                                               # rate_ingested_idx
```

### 1. Latest rate per provider  → `rate_latest_idx`
Postgres `DISTINCT ON` picks the newest row per group; the leading index columns
match the `DISTINCT ON` + `ORDER BY`, so it's an index scan, not a sort.

```sql
SELECT DISTINCT ON (provider_id, rate_type) *
FROM   rate
-- optional: WHERE rate_type = %s
ORDER  BY provider_id, rate_type, effective_date DESC, observed_at DESC;
```

### 2. Rate change over the last 30 days for a given type  → `rate_type_date_idx`
Filter by `rate_type` and a 30-day `effective_date` window; the composite index
covers both the equality and the range.

```sql
SELECT provider_id, effective_date, rate_value
FROM   rate
WHERE  rate_type = %s
  AND  effective_date >= (CURRENT_DATE - INTERVAL '30 days')
ORDER  BY provider_id, effective_date;
```

### 3. All records ingested in a given 24-hour window  → `rate_ingested_idx`
A range scan on `ingested_at` (our ingest time — distinct from the source's).

```sql
SELECT *
FROM   rate
WHERE  ingested_at >= %s
  AND  ingested_at <  %s;   -- e.g. [T, T + 24h)
```

### Bonus: the dashboard board (`/rates/summary`) → also `rate_latest_idx`
The redesigned board needs, per series, the latest rate plus a sparkline and 30-day
change. Rather than one `/history` call per row, one endpoint returns it all. It reuses
query 1 for the head value, and one window query for the sparkline: a `DISTINCT ON`
daily collapse (served by `rate_latest_idx`, same as query 1) wrapped in a
`ROW_NUMBER()` that keeps each series' most recent 30 distinct dates. The window is
data-anchored (last 30 dates *with data*), so it matches the history chart on the
seed's sparse-recent data rather than returning an empty calendar window.

```sql
WITH daily AS (
  SELECT DISTINCT ON (provider_id, rate_type, effective_date)
         provider_id, rate_type, effective_date, rate_value
  FROM   rate                              -- optional: WHERE rate_type = %s
  ORDER  BY provider_id, rate_type, effective_date DESC, observed_at DESC, id DESC
)
SELECT provider_id, rate_type, rate_value
FROM   (SELECT *, ROW_NUMBER() OVER (PARTITION BY provider_id, rate_type
                                     ORDER BY effective_date DESC) AS rn
        FROM daily) ranked
WHERE  rn <= 30
ORDER  BY provider_id, rate_type, effective_date;
```

---

## Tradeoffs considered

- **Provider as a dimension table vs. a plain string column.** The dimension costs a
  join but fixes casing once and gives stable API slugs; at 10 providers the join is
  free. Worth it.
- **Keeping all intra-day observations vs. one row per day.** Keeping them all makes
  the fact table larger, but it's the only correct choice for a time series: the
  history endpoint and chart need every observation.
- **`numeric(6,4)` vs. `float8`.** Numeric for correctness; the tiny size and speed
  cost is irrelevant at this scale.
- **No materialized "latest" view.** `DISTINCT ON` plus the composite index is fast
  enough for 10 providers × 5 types. A materialized view would be premature, and is
  noted as a scale-up option in DECISIONS.md.
- **JSONB payload on the raw table.** Costs storage (roughly the raw row per record)
  but is what makes failed parses replayable, which is a requirement here, not
  overhead.
