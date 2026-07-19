# DECISIONS.md

The engineering thinking behind Rate-Tracker: what I assumed, how I handle the
messy seed data, one tradeoff I made on purpose, and the one thing I'd change with
more time. (The README covers how to run it; this covers why it's built this way.)

---

## 1. Assumptions

Things I assumed about the data, use case, or environment that shaped the design.
Each is something a production engineer should verify before deploying.

- **Multiple readings per provider+type+day are real observations, not duplicates.**
  Almost every row in the seed shares a `(provider, rate_type, effective_date)` with
  other rows but carries a distinct `raw_response_id` and timestamp. I treat the data
  as a time series and dedupe only on `raw_response_id` (the unique source event id).
  Collapsing on the business key would have destroyed the history the dashboard
  renders. *Verify:* confirm with the data producer that intra-day multiplicity is
  real and not an upstream bug.
- **A rate above 25% is impossible for these products** (mortgages, savings), so I
  quarantine anything above that ceiling (configurable via `RATE_OUTLIER_CEILING`).
  The seed has values up to 97.4%. *Verify:* confirm the ceiling with the business;
  it's a policy, not a law of nature.
- **The parquet codec isn't what the brief says.** The brief says Snappy; the file is
  actually ZSTD. I never hardcode the codec, since pyarrow auto-detects it. *Verify:*
  don't assume Snappy in any downstream tooling.
- **"Ingestion timestamp" means *our* ingest time.** I store two timestamps:
  `observed_at` (the source's `ingestion_ts`, when the rate was published) and
  `ingested_at` (when we wrote it). The 24-hour-window query uses `ingested_at`.
  *Verify:* confirm which timestamp the "24h window" question refers to.
- **There's no live rate source.** The brief describes a scraper, but there's no real
  endpoint. The scheduled worker re-ingests the seed through the `RateSource`
  interface as a stand-in; the HTTP scraper path (`HttpRateSource`) is built and
  mock-tested, ready to point at a real endpoint. *Verify:* wire real provider URLs
  before this is anything but a demo.
- **Currency is single (USD).** The seed is USD-only, with dirty variants (`usd`,
  `US Dollar`). I normalize to ISO `USD` and do no FX. *Verify:* if multi-currency
  arrives, comparison-by-rate needs a currency-aware model.
- **The data is gappy, and "recent" isn't "today".** The seed's dense data ends around
  2026-03-26 with a few sparse later points, so a calendar window ending "today"
  (2026-07) renders a near-empty chart. I default the history window to the 30 most
  recent days that actually have data, and offer `granularity=daily` (one point per
  day) so the ~36 intraday readings per day collapse into a clean line. *Verify:* in a
  live system where data is current this is just "last 30 days"; the behaviour only
  diverges for stale or gappy data.

---

## 2. Idempotency strategy: how the worker handles the seed's issues

The seed file has seven distinct data issues. The worker handles them in two layers:
structural idempotency (safe re-runs) and data-quality handling (clean vs.
quarantine). Running `python manage.py seed_data` any number of times converges to
the same DB state.

### Structural idempotency (safe re-runs)

The database is the source of truth, not application bookkeeping:

- Every source row lands in `raw_rate_response`, keyed by a unique `response_id` (the
  parquet `raw_response_id`). Landing uses `bulk_create(ignore_conflicts=True)`, so a
  row already seen is skipped, not duplicated.
- Each valid row promotes to `rate` through a one-to-one link on `response_id`, also
  with `ignore_conflicts`, so a source event maps to at most one cleaned rate.
- Repeated `response_id`s within a single batch are de-duplicated in Python before the
  bulk insert, so one `INSERT` never carries a duplicate key.
- Each batch runs in its own transaction, so a mid-load failure leaves a consistent
  partial state that the next (idempotent) run finishes.

Because `ignore_conflicts` hides how many rows were actually inserted, the `landed`
and `promoted` counts are measured as DB row-count deltas rather than guessed from the
input size.

### The seven issues and how each is handled

| # | Issue (seed) | Example | Handling |
|---|---|---|---|
| 1 | Provider casing | `HSBC` / `Hsbc` / `hsbc` | Normalize to one `provider` row keyed by slug; display name resolved via a small acronym-aware map |
| 2 | Currency variants | `USD` / `usd` / `US Dollar` | Normalize to ISO `USD` |
| 3 | Null rate | `rate_value = null` (200 rows) | Quarantine as `null_rate` |
| 4 | Negative rate | down to −1.84% (15 rows) | Quarantine as `non_positive_rate` |
| 5 | Absurd outlier | up to 97.4% (15 rows) | Quarantine as `outlier_rate` (> 25%) |
| 6 | Future effective date | up to 2026-09-22 (17 rows) | Quarantine as `future_effective_date` |
| 7 | Business-key duplicates | many readings per provider+type+day | Kept — real observations, deduped only on `raw_response_id` |

Quarantine, not drop. Rejected rows aren't silently discarded: they stay in
`raw_rate_response` with `status='rejected'` and a reason code, alongside the full raw
payload. So a fix to the cleaning rules can replay them, and an operator can query
exactly why any row was dropped. This covers the HTTP scraper too: a timeout, HTTP
error, or unparseable body is landed as a `scrape_failed` reject (with its URL and
error) under a deterministic id, so the scraper path has the same replay guarantee as
the seed path. Two more guards handle feeds dirtier than the seed: an unknown currency
is quarantined (`unknown_currency`) rather than coerced into a wrong 3-letter code,
and a missing or unparseable `raw_response_id` is landed under a payload-derived
deterministic id (`bad_response_id`) instead of crashing the batch. Against the real
1M-row file the counts are `null_rate: 200, future_effective_date: 17,
outlier_rate: 15, non_positive_rate: 15`, which matches the data profile.

---

## 3. One tradeoff I made consciously

A shared-secret bearer token for the ingest webhook, instead of DRF's DB-backed
`TokenAuthentication`.

- Option A (chosen): a single `INGEST_API_TOKEN` from the environment, checked by a
  small custom `BearerTokenAuthentication` class.
- Option B (rejected): DRF's `TokenAuthentication`, which needs a `User` table, a
  `Token` table, and a token-issuance flow.

Given a 48-hour window and a machine-to-machine webhook with no human users, the
User/Token apparatus buys nothing here: there's no per-user authorization, no login,
no session. A rotating shared secret injected via env is the right weight for the
threat model, keeps the schema focused on the domain, and still satisfies "bearer
token via DRF authentication classes, no external auth service." The cost I accept is
no per-caller identity or revocation. If we later need multiple ingest clients with
independent credentials, this is the first thing to replace (a DB-backed token, or a
JWT/OIDC layer).

A second, smaller tradeoff: `pip` and a pinned `requirements.txt` over `uv` or Poetry,
so any reviewer can read the dependency story instantly and the Docker build needs no
extra tooling. And Python 3.13 not 3.14, Postgres 18 not 19-beta, Node 24 LTS not 26:
the latest versions all the dependencies fully support, not the newest possible.

---

## 4. One thing I would change with more time

Replace the 60-second polling refresh with Server-Sent Events pushed from an
ingest-triggered signal, because polling is both stale and wasteful.

Today the dashboard re-fetches `/rates/latest` every 60s whether or not anything
changed, and a rate can be up to 60s stale on screen. With more time I'd:

1. On a successful ingest (webhook or scheduled), publish an event to a Redis pub/sub
   channel. I already invalidate the cache at exactly that point, so the hook exists.
2. Expose an SSE endpoint (Django ASGI plus an async view) that subscribes to the
   channel and streams a "rates updated" event to connected browsers.
3. On the client, revalidate the affected SWR keys when the event arrives.

The UI would then update within a second of a real change and make no requests when
nothing changes. I chose polling for the assessment because it's robust and ships in
minutes; SSE/WebSockets need connection lifecycle, backpressure, and reconnection
handling that isn't worth the 48-hour risk. I'd also add a COPY-based fast path for
the initial 1M-row seed (roughly 10x faster than ORM `bulk_create`, at the cost of the
per-row validation and raw-landing story), and a materialized "latest" view if the
`DISTINCT ON` query ever became a hotspot at higher cardinality.

---

## 5. The dashboard rewrite and the live deploy

Two additions beyond the core assessment: a redesigned dashboard ("the rates desk")
and an optional Railway deploy. Both are additive — local `docker compose up` and the
existing API contract are unchanged.

**A dedicated `/rates/summary` endpoint, not N browser calls.** The redesigned board
shows, per provider, an inline sparkline and a 30-day change chip. The naive way to
get that is a `/history` fetch per visible row (~10+ requests); a reviewer would
rightly flag the N+1. Instead one cached endpoint returns latest + change + a
downsampled series for every series in a single response. It mirrors `/latest`
exactly — same `?type=` contract, same Redis write-through invalidation (a single
`invalidate_latest()` now busts both namespaces, since any write that changes the
latest rate also changes its summary). Two indexed queries back it: `latest_rates()`
for the head value, and one window-function query for the sparklines.

**The sparkline window is data-anchored, matching the chart — not a calendar window.**
My first cut used `today − 30 days`, which returns almost nothing on this seed (dense
data ends ~2026-03, "today" is 2026-07). The fix: take the most recent 30 distinct
dates that *have data* per series (a `ROW_NUMBER()` over the daily-collapsed rows) —
exactly the rule the history chart already uses. So the board's sparkline and the
drill-in chart always agree, and `change_30d` is the sparkline's own last − first, so
the chip can never disagree with the line it sits next to.

**Deploy: one platform keeping the real worker, not a mocked-out subset.** The live
target is Railway, chosen over a truly-free managed split precisely to keep a real
Celery worker running the scheduled ingest rather than faking it. Two small,
backward-compatible changes make it portable: settings accept a single `DATABASE_URL`
(managed hosts supply one) and fall back to the discrete `POSTGRES_*` vars local
compose sets; and the seed/scheduled-ingest can be bounded to a window.

*What actually shipped differs from the six-service ideal, and the gap is the
interesting part.* Railway's free plan caps a project at 5 resources, so the deployed
topology is **five** services — `beat` is folded into the worker as `celery worker
--beat` rather than running as its own process. Local `docker compose` still runs the
full six-service split, which stays the canonical topology; the merge is a deploy-tier
concession, not a design change. Celery's docs call embedded beat a development
convenience (one scheduler process is fine here because the worker is single-replica,
but it would not survive horizontal scaling — with two replicas you would get two
schedulers and duplicate ingests). Splitting `beat` back out is a one-line change once
the plan allows a 6th resource. See [DEPLOY.md](DEPLOY.md) for the exact settings.

**The deploy seeds a bounded, representative slice — sized by measurement, not guess.**
The full seed is ~1M rows with a JSONB raw payload each, far heavier than a free tier
wants. The deployed slice is `--since 2026-03-01` (~47.7k source rows): all 10 providers
× 5 rate types, enough for sparklines and the 30-day delta, on a 500 MB volume. That
number was arrived at the hard way — `--since 2026-01-01` (~156k rows) exhausted the
volume mid-load and left Postgres crash-looping, because WAL churn during a bulk insert
needs headroom well beyond the final table size. Two knobs came out of it: `SEED_SINCE`
bounds the scheduled re-ingest, and `INGEST_BATCH_SIZE` bounds *peak memory* (a whole
batch is materialised as Python objects before the bulk insert — 50k rows peaked at
~590 MB RSS and got the 1 GB worker OOM-killed; 5k peaks at ~430 MB). I used a
*fixed* `--since` date rather than a clock-relative `--days` on purpose: the seed is
static and its dense data ends before "today", so a fixed date targets it regardless of
the deploy server's clock. Loading stays idempotent, so a re-run or the scheduled task
converges to the same state.

---

## Known limitations

Honest edges a production engineer should know about. None affects the seed or the
assessment run, but each matters for a real feed:

- **Quarantined rows aren't re-validated.** A row rejected as `future_effective_date`
  isn't auto-promoted once its date passes; its raw record stays flagged and would
  need a manual replay. The other reject reasons (null, negative, outlier,
  missing-date) are deterministic and never flip, so only future-dated rows are
  affected, and the seed's future rows stay future well past the assessment window.
- **Ingestion assumes a single writer.** `landed`/`promoted`/`rejected` are computed
  as DB deltas, which are exact single-threaded; a manual `seed_data` overlapping the
  hourly Beat task could over-report the counts (DB state and idempotency are
  unaffected). The 1-hour Beat interval far exceeds the ~2-minute run time. A
  production version would take a Postgres advisory lock around ingestion.
- **The ingest webhook returns a 400 without landing the payload, on purpose.** Unlike
  the bulk feed, which can't reject inline and so quarantines, a synchronous
  authenticated caller gets immediate structured feedback and can fix and resend, so a
  rejected `POST /rates/ingest` writes nothing. The "quarantine, not drop" guarantee
  applies to the feed and scraper paths, where replay is the only recourse.

## What is complete vs. deferred

**Complete:** all required scope — ingestion and persistence, the API, and Docker/ops
— plus the bonus frontend (redesigned; see section 5), the `/summary` endpoint that
powers it, the observability stub, and an optional Railway deploy. 96 backend tests
pass; the full 1M-row seed loads and cleans correctly; the frontend builds and renders
against the real API.

**Deferred (YAGNI for 48h):** SSE/WebSocket push (see section 4), multi-currency FX, a
provider-onboarding UI, an exhaustive frontend test suite (the backend carries the
test weight), Git LFS for the parquet, and a COPY-based bulk seed path. Each is a
conscious defer, not an oversight.
