# Rate-Tracker

A small, production-shaped app that scrapes, cleans, stores, serves, and renders
interest-rate data, then refreshes it automatically. Built for the Forbes Advisor /
Marketplace Senior Full-Stack take-home.

```
parquet seed / HTTP scraper  →  idempotent ingestion (clean + quarantine)
        →  PostgreSQL  →  typed DRF API (cached, authed webhook)
        →  Next.js dashboard: market highlights, a sortable rates board with inline
           sparklines + basis-point deltas, a 30-day chart — refreshes every 60s
```

- Backend: Django 6, DRF 3.17, Celery 5.6, PostgreSQL 18, Redis 8, Python 3.13
- Frontend: Next.js 16, React 19, Recharts, SWR, Node 24 — "the rates desk": a
  light/dark financial dashboard (KPI strip, live status, dedicated mobile layout)
- Everything runs with one `docker compose up`.

See [DECISIONS.md](DECISIONS.md) for the engineering rationale (assumptions,
idempotency, tradeoffs) and [schema.md](schema.md) for the database design. A live
deploy to Railway (a real Celery worker running the scheduled ingest, with beat
embedded to fit the free plan's 5-resource cap) is documented in
[DEPLOY.md](DEPLOY.md) — optional; local `docker compose up` stays the canonical
path and keeps worker and beat as separate services.

---

## Prerequisites

- Docker and Docker Compose v2 (`docker compose version`). Nothing else; Python and
  Node run inside the containers.
- Ports 3000 (dashboard) and 8000 (API) free.
- `make` is optional; the raw `docker compose` commands are shown alongside it.

---

## How to run locally

```bash
# 1. Build and start the whole stack. `make up` auto-creates .env from the template
#    on first run (defaults work out of the box; change secrets before real use).
make up                    # or: cp .env.example .env && docker compose up --build -d

# 2. Load the sample data (~1M rows; idempotent, safe to re-run).
make seed                  # or: docker compose exec web python manage.py seed_data
```

> No `.env` is needed to boot: `docker compose up` works on a fresh clone, because
> every Compose value falls back to a working local default. Copy `.env.example` to
> `.env` only when you want to override a secret or setting.

Open http://localhost:3000 for the dashboard. The API is at
http://localhost:8000/api/rates/latest.

> Fail-fast: if a required env var is missing, the app stops immediately with
> `Missing required env var X — <what it's for>`, rather than crashing later.

> On timing: the first `make up` builds both images (`pip install` and `next build`),
> which takes a few minutes on a cold clone; later starts come up in seconds behind
> healthcheck gating. Loading the full 1M-row seed is a separate step (`make seed`,
> ~2–3 min) — the dashboard is reachable before then and populates once the seed
> completes.

---

## The API

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api/rates/latest?type=<rate_type>` | Latest rate per provider (+type). Redis-cached. |
| GET | `/api/rates/summary?type=<rate_type>` | Latest rate plus a 30-day change and sparkline series per provider, in one call. Redis-cached. Powers the dashboard's board + KPI strip. |
| GET | `/api/rates/history?provider=<slug>&type=<rate_type>&from=&to=&granularity=daily` | Bounded, paginated time-series. `granularity` is `daily` or `raw` (an unknown value is a 400); an unknown `provider` slug is a 404. Default window = the 30 most recent days with data. |
| POST | `/api/rates/ingest` | Bearer-auth webhook. Strict validation (unknown fields rejected), structured errors. |
| GET | `/api/healthz` | Cheap liveness probe (no DB) used by the container healthcheck. |

```bash
# Read (no auth):
curl "http://localhost:8000/api/rates/latest?type=30yr_fixed_mortgage"
curl "http://localhost:8000/api/rates/history?provider=chase&type=5yr_arm_mortgage"

# Write (bearer token from your .env INGEST_API_TOKEN):
curl -X POST http://localhost:8000/api/rates/ingest \
  -H "Authorization: Bearer $INGEST_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"Chase","rate_type":"5yr_arm_mortgage","rate_value":6.42,
       "effective_date":"2026-07-19","ingestion_ts":"2026-07-19T10:00:00Z","currency":"USD"}'
```

Rate types: `30yr_fixed_mortgage`, `15yr_fixed_mortgage`, `5yr_arm_mortgage`,
`savings_1yr_fixed`, `savings_easy_access`.

---

## How to run tests

```bash
make test
# or, directly against the running web container:
docker compose exec web pip install -q -r requirements-dev.txt
docker compose exec -e DJANGO_DEBUG=false web pytest -q
```

96 backend tests cover cleaning and validation for all seven data issues (plus
unknown currency and unparseable ids), the HTTP-mock parser test, idempotent
ingestion, replay-landing of failed scrapes, the four read/write API endpoints
(latest, summary's data-anchored sparkline + change, history pagination bounds,
bearer auth, strict validation, structured errors including the 404/400 edges),
caching and invalidation, the bounded/`--since` seed path, `DATABASE_URL`
portability, and the slow-query warning on both the API and the ingestion worker.
The frontend is type-checked and built as part of its Docker image.

---

## Architecture rationale (the non-obvious bits)

- Two-table ingest (raw landing + cleaned fact). Raw rows land first, keyed by a
  unique `response_id`, so re-runs are idempotent at the DB level and rejected rows
  stay replayable. Only valid rows are promoted to `rate`. Full reasoning in
  [DECISIONS.md](DECISIONS.md#2-idempotency-strategy-how-the-worker-handles-the-seeds-issues).
- Celery + Beat for scheduling (not cron-in-a-container), for retries, task-level
  observability, and running locally under compose.
- Cache invalidation is write-through: every ingest busts the `rates:latest:*` keys,
  and the short TTL is only a safety net.
- Bearer token via a small DRF auth class, not a DB-backed User/Token table — the
  right weight for a machine webhook. See the tradeoff in DECISIONS.md.
- Structured JSON logging, no `print` in application code; a middleware warns on any
  SQL query over 200ms.

---

## What's included vs. deferred

Included: all required scope (ingestion + persistence, API, Docker/ops) plus the
optional Next.js dashboard (a redesigned "rates desk" — KPI highlights, a sortable
board with sparklines and basis-point deltas, light/dark), the `/summary` endpoint
that powers it, the observability stub, and an optional Railway deploy ([DEPLOY.md](DEPLOY.md)).

Deferred (conscious, documented in DECISIONS.md §4): SSE/WebSocket push in place of
60s polling, multi-currency FX, a COPY-based fast seed path, and an exhaustive
frontend test suite. The backend carries the test weight by design.

---

## Project layout

```
backend/    Django project (config/) + rates app (models, ingestion, sources, api, tests)
frontend/   Next.js dashboard (app/, components/, lib/) + its own railway.json
data/       rates_seed.parquet (mounted read-only into the containers)
DECISIONS.md · schema.md · DEPLOY.md · docker-compose.yml · Makefile · .env.example
railway.json (root: the shared backend build config, per DEPLOY.md)
```
