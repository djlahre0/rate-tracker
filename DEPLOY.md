# Deploying Rate-Tracker to Railway

Local `docker compose up` remains the canonical way to run this project (see
[README](README.md)). This guide is the **optional live deploy** used to hand an
evaluator a URL. It puts the whole stack — **web, Celery worker, Celery beat,
frontend, Postgres, Redis** — on [Railway](https://railway.com), keeping the real
six-service topology rather than mocking anything out.

> **Cost & honesty.** Railway's Hobby plan bills usage against a small monthly
> credit (a trial credit covers an evaluation window). This is *not* indefinitely
> free — it's the deliberate tradeoff for keeping an always-on worker + beat, which
> truly-free tiers don't offer. See [DECISIONS.md](DECISIONS.md) for the reasoning.

The repo ships Railway config-as-code: [`backend/railway.json`](backend/railway.json)
and [`frontend/railway.json`](frontend/railway.json) set the Dockerfile builder,
start command, and healthcheck. Everything below is done once in the dashboard.

---

## What gets deployed

```
                    ┌── frontend (Next.js, public URL) ──┐
   evaluator ─────► │                                    │  calls
                    └──────────────► web (Django/gunicorn, public URL)
                                        │  ├── Postgres (plugin)
                       worker (celery) ─┤  └── Redis (plugin)
                       beat   (celery) ─┘
```

Six Railway services in one project. `web`, `worker`, and `beat` all build from
`backend/` (same image, different start command); `frontend` builds from `frontend/`.

---

## Prerequisites

- A Railway account and this repo pushed to GitHub.
- The [Railway CLI](https://docs.railway.com/guides/cli) (`npm i -g @railway/cli`),
  used once to load the seed data.

---

## Step 1 — Project + managed data stores

1. **New Project → Deploy from GitHub repo**, and pick this repo.
2. Add **Postgres**: *New → Database → Add PostgreSQL*. It exposes `DATABASE_URL`.
3. Add **Redis**: *New → Database → Add Redis*. It exposes `REDIS_URL`.

## Step 2 — `web` service (Django API)

Railway creates a service from the repo. Configure it:

- **Settings → Root Directory:** `backend` (so it uses `backend/railway.json` +
  `backend/Dockerfile`). Start command and `/api/healthz` healthcheck come from the JSON.
- **Settings → Networking → Generate Domain** (note it, e.g. `https://web-xxxx.up.railway.app`).
- **Variables** (see the [reference](#environment-variable-reference) below):

  ```
  DJANGO_SECRET_KEY=<long random string>
  DJANGO_DEBUG=false
  DJANGO_ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}}
  INGEST_API_TOKEN=<long random string>
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  REDIS_URL=${{Redis.REDIS_URL}}
  CORS_ALLOWED_ORIGINS=<frontend URL from Step 5, add once known>
  SEED_SINCE=2026-01-01
  RUN_MIGRATIONS=true
  ```

  `${{Postgres.DATABASE_URL}}` / `${{Redis.REDIS_URL}}` are Railway *reference
  variables* — they resolve to the plugin's private connection string. The
  container entrypoint runs `migrate` on boot because `RUN_MIGRATIONS=true`.

## Step 3 — `worker` service (Celery worker)

- *New → GitHub Repo → same repo*. **Root Directory:** `backend`.
- **Settings → Custom Start Command:** `celery -A config worker --loglevel=info`
- **Variables:** same as `web`, but `RUN_MIGRATIONS=false` and **no** domain
  (workers don't serve HTTP). Tip: use Railway's *shared variables* or copy the set.

## Step 4 — `beat` service (Celery scheduler)

- Same as the worker, with **Custom Start Command:** `celery -A config beat --loglevel=info`
- `RUN_MIGRATIONS=false`, no domain. `SEED_SINCE=2026-01-01` bounds each scheduled
  re-ingest to the seed's dense window, so the hourly job stays cheap and idempotent.

## Step 5 — `frontend` service (Next.js)

- *New → GitHub Repo → same repo*. **Root Directory:** `frontend`.
- **Networking → Generate Domain** (note it, e.g. `https://app-xxxx.up.railway.app`).
- **Variables:**

  ```
  NEXT_PUBLIC_API_URL=<web URL from Step 2>
  ```

  This is read at **build time** (baked into the browser bundle via the Dockerfile
  `ARG`), so a change requires a redeploy.

## Step 6 — Wire the two domains together

Now that both URLs exist, close the loop:

- On **`web`**, set `CORS_ALLOWED_ORIGINS` to the **frontend** URL and redeploy.
- On **`frontend`**, confirm `NEXT_PUBLIC_API_URL` is the **web** URL and redeploy.

(They reference each other, so both are set only once both domains are generated.)

## Step 7 — Load the seed data (one-off)

Migrations already ran on the `web` deploy. Load a bounded, representative slice —
all 10 providers × 5 rate types over the seed's dense window — from your local clone
straight into the deployed database:

```bash
railway link                       # select the project
# Grab the PUBLIC Postgres URL: Railway → Postgres → Variables → DATABASE_PUBLIC_URL
DATABASE_URL="<DATABASE_PUBLIC_URL>" \
DJANGO_SECRET_KEY=x INGEST_API_TOKEN=x \
POSTGRES_DB=x POSTGRES_USER=x POSTGRES_PASSWORD=x REDIS_URL=redis://localhost:6379/0 \
  backend/.venv/Scripts/python backend/manage.py seed_data --since 2026-01-01
```

- The parquet lives in your **local** clone (`data/`), so this streams it into the
  remote DB — no need to bake a large file into the image. Use the **public** DB URL
  (`DATABASE_PUBLIC_URL`); the private `*.railway.internal` host isn't reachable from
  your machine. The dummy `POSTGRES_*`/`REDIS_URL` values just satisfy fail-fast
  startup; `DATABASE_URL` wins for the actual connection and cache invalidation is
  best-effort, so Redis needn't be reachable.
- `--since 2026-01-01` targets the seed's dense region (the data thins out after
  2026-03; a smaller subset than the full ~1M rows keeps storage light). Loading is
  idempotent — safe to re-run. Prefer a lighter demo? Use `--since 2026-03-01`.

## Step 8 — Verify

```bash
curl https://<web>/api/healthz                                  # {"status":"ok"}
curl "https://<web>/api/rates/summary?type=30yr_fixed_mortgage" # rows with spark + change
```

Open the **frontend** URL: the board fills, sparklines and 30-day deltas render, the
chart draws, and "updated Ns ago" ticks. Check the `beat` logs for the scheduled
`ingest_rates` firing on cadence.

---

## Environment variable reference

| Variable | web | worker | beat | frontend | Value |
|---|:--:|:--:|:--:|:--:|---|
| `DJANGO_SECRET_KEY` | ✓ | ✓ | ✓ | | long random string |
| `DJANGO_DEBUG` | ✓ | ✓ | ✓ | | `false` |
| `DJANGO_ALLOWED_HOSTS` | ✓ | ✓ | ✓ | | `${{RAILWAY_PUBLIC_DOMAIN}}` (or `*`) |
| `INGEST_API_TOKEN` | ✓ | ✓ | ✓ | | long random string |
| `DATABASE_URL` | ✓ | ✓ | ✓ | | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | ✓ | ✓ | ✓ | | `${{Redis.REDIS_URL}}` |
| `CORS_ALLOWED_ORIGINS` | ✓ | | | | frontend URL |
| `SEED_SINCE` | ✓ | ✓ | ✓ | | `2026-01-01` |
| `RUN_MIGRATIONS` | `true` | `false` | `false` | | migrate on boot (web only) |
| `NEXT_PUBLIC_API_URL` | | | | ✓ | web URL (build-time) |

Optional: `INGEST_INTERVAL_SECONDS` (beat cadence, default 3600),
`RATE_OUTLIER_CEILING`, `SLOW_QUERY_SECONDS`. All are documented in
[`.env.example`](.env.example).

---

## Notes & gotchas

- **`web` binds `$PORT`.** `backend/railway.json` starts gunicorn on Railway's
  injected `$PORT`; the frontend's standalone Next server honors `$PORT` too.
- **Worker/beat need no domain or healthcheck** — they're background processes.
- **Redeploy the frontend** after changing `NEXT_PUBLIC_API_URL` — it's compiled in.
- **Bring it down** by deleting the project (or pausing services) to stop billing.
