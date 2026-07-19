# Deploying Rate-Tracker to Railway

Local `docker compose up` remains the canonical way to run this project (see
[README](README.md)). This guide is the **live deploy** used to hand an evaluator a
URL. It puts the stack — **web, Celery worker (with embedded beat), frontend,
Postgres, Redis** — on [Railway](https://railway.com), keeping a real worker doing
real scheduled ingestion rather than mocking anything out.

> **Cost & honesty.** This fits Railway's **free plan**, which caps a project at
> **5 resources**, gives each service **1 GB memory**, and each volume **500 MB**.
> Those three limits shape most of the configuration below. Usage still bills against
> a trial credit, so it is not indefinitely free. See [DECISIONS.md](DECISIONS.md).

---

## What gets deployed

```
                    ┌── frontend (Next.js, public URL) ──┐
   evaluator ─────► │                                    │  calls
                    └──────────────► web (Django/gunicorn, public URL)
                                        │  ├── Postgres (managed)
                    worker (celery ─────┤  └── Redis (managed)
                     worker --beat)     │
```

**Five** Railway services. `web` and `worker` build the same image from
`backend/Dockerfile`; `frontend` builds from `frontend/`.

> **Why beat isn't its own service.** The free plan's 5-resource cap leaves no room
> for a 6th. `beat` is folded into the worker via `celery worker --beat`. Local
> compose still runs them as separate services — that split is the canonical
> topology. This is safe only because the worker is single-replica; two replicas
> would mean two schedulers and duplicate ingests. To split it back out on a paid
> plan, create a `beat` service with start command `celery -A config beat
> --loglevel=info`, `RUN_MIGRATIONS=false`, and no domain, then drop `--beat` here.

---

## Build layout

The backend image builds with the **repo root as context** (not `backend/`) so it can
`COPY data/` — the seed parquet has to be *inside* the image for the scheduled ingest
to work on a host with no volume mount:

| File | Role |
|---|---|
| [`railway.json`](railway.json) | Root: shared backend build config (`DOCKERFILE`, `backend/Dockerfile`). Read by `web` and `worker`, whose root directory is `/`. |
| [`frontend/railway.json`](frontend/railway.json) | Frontend build + start config. Read only by `frontend`, whose root directory is `/frontend`. |
| [`.dockerignore`](.dockerignore) | Root-level, since the backend build context is the root. Must **not** exclude `data/`. |

Per-service start commands, healthcheck, and root directory live in Railway service
settings (a single `railway.json` can't differ per service when two services share a
root directory).

---

## Prerequisites

- A Railway account and the [Railway CLI](https://docs.railway.com/guides/cli)
  (`npm i -g @railway/cli`), then `railway login`.
- A local clone (the seed load streams the parquet from your machine).

## Step 1 — Project + managed data stores

```bash
railway init --name rate-tracker
railway add --database postgres --json     # service name: Postgres
railway add --database redis --json        # service name: Redis
```

The service names matter: `${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}`
reference them by name and are case-sensitive.

## Step 2 — Create the app services

```bash
railway add --service web --json
railway add --service worker --json
railway add --service frontend --json
```

## Step 3 — Domains

```bash
railway domain --service web --port 8000 --json
railway domain --service frontend --port 3000 --json
```

Note both URLs — they reference each other in Step 4.

> **The target port must match what the process binds.** Railway injects its own
> `PORT` (8080) unless you set one. If the domain targets 8000 but gunicorn binds
> 8080, the edge returns **502 despite a green deployment**. Both services below pin
> `PORT` explicitly so the two always agree.

## Step 4 — Variables

`web`:

```
DJANGO_SECRET_KEY=<long random string>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app
INGEST_API_TOKEN=<long random string>
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
CORS_ALLOWED_ORIGINS=<frontend URL from Step 3>
SEED_SINCE=2026-03-01
RUN_MIGRATIONS=true
PORT=8000
```

`worker`: same, except `DJANGO_ALLOWED_HOSTS=*`, `RUN_MIGRATIONS=false`, no
`PORT`/`CORS_ALLOWED_ORIGINS`, plus `INGEST_BATCH_SIZE=5000`.

`frontend`: `NEXT_PUBLIC_API_URL=<web URL from Step 3>` and `PORT=3000`.

> **`healthcheck.railway.app` is not optional.** Railway's healthcheck probes with
> that `Host` header, so omitting it makes Django answer `400 DisallowedHost` and the
> deploy fails after burning the full retry window.

> **`NEXT_PUBLIC_API_URL` is baked at build time** into the browser bundle via the
> Dockerfile `ARG`. Changing it requires a rebuild, not just a restart.

## Step 5 — Service settings

Start commands, healthcheck, and root directory (dashboard, or the API):

| Service | Setting | Value |
|---|---|---|
| `web` | Start command | `sh -c '/app/entrypoint.sh gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3'` |
| `web` | Healthcheck path | `/api/healthz` |
| `worker` | Start command | `sh -c '/app/entrypoint.sh celery -A config worker --beat --loglevel=info --concurrency=1'` |
| `frontend` | Root directory | `/frontend` |

> **A custom start command replaces the image `ENTRYPOINT`.** `entrypoint.sh` is what
> waits for Postgres and runs `migrate`, so a plain `gunicorn ...` start command
> silently skips migrations — the app boots fine and then every query fails on
> missing tables. Both backend commands above invoke `/app/entrypoint.sh` explicitly.

> **`--concurrency=1` is deliberate.** Each prefork child loads Django, and the
> ingest peaks around 430 MB on its own; two children plus the parent exceed the
> 1 GB cap and the worker gets OOM-killed mid-task (`WorkerLostError: signal 9`).

## Step 6 — Deploy

```bash
railway up --service web       --detach -m "web"
railway up --service worker    --detach -m "worker"
railway up --service frontend  --detach -m "frontend"
```

Poll to a terminal state — a detached `up` returning only means *queued*:

```bash
railway deployment list --service web --environment production --json   # check .status
```

> **Changing a service setting requires `railway up`, not `railway redeploy`.**
> `redeploy` replays the previous deployment's config snapshot: variable changes take
> effect (they're read at runtime) but a changed **start command does not**. That
> combination is confusing to debug — the deploy goes green with the old command.

## Step 7 — Load the seed data (one-off)

Migrations already ran on the `web` deploy. Stream a bounded slice from your local
clone into the deployed database:

```bash
# Postgres → Variables → DATABASE_PUBLIC_URL (the private *.railway.internal host
# is not reachable from your machine).
DATABASE_URL="<DATABASE_PUBLIC_URL>" \
DJANGO_SECRET_KEY=x INGEST_API_TOKEN=x \
POSTGRES_DB=x POSTGRES_USER=x POSTGRES_PASSWORD=x REDIS_URL=redis://localhost:6379/0 \
  backend/.venv/Scripts/python backend/manage.py seed_data --since 2026-03-01
```

The dummy `POSTGRES_*`/`REDIS_URL` values just satisfy fail-fast startup;
`DATABASE_URL` wins for the connection, and cache invalidation is best-effort so
Redis needn't be reachable (it logs one warning). Loading is idempotent.

> **Do not raise this window without raising the volume.** `--since 2026-01-01`
> (~156k rows) exhausts the 500 MB volume *mid-load* — WAL churn during bulk insert
> needs far more headroom than the final table size. Postgres then cannot restart,
> because replaying WAL itself needs free space; the only fix is recreating the
> service. `--since 2026-03-01` (~47.7k rows) settles at ~203 MB / 500 MB.

## Step 8 — Verify

```bash
curl https://<web>/api/healthz                                    # {"status":"ok"}
curl "https://<web>/api/rates/summary?type=30yr_fixed_mortgage"   # rows with spark + change

# CORS actually allows the browser origin:
curl -i "https://<web>/api/rates/latest" -H "Origin: https://<frontend>" \
  | grep -i access-control-allow-origin
```

Open the **frontend** URL: the board fills, sparklines and 30-day deltas render, the
chart draws. To prove the scheduled path without waiting for the hourly tick, enqueue
it directly and watch the worker logs (`railway logs --service worker --deployment`)
for `ingest_start` → `ingest_end` → `succeeded in ...`:

```bash
REDIS_URL="<REDIS_PUBLIC_URL>" DATABASE_URL="<DATABASE_PUBLIC_URL>" \
DJANGO_SECRET_KEY=x INGEST_API_TOKEN=x POSTGRES_DB=x POSTGRES_USER=x POSTGRES_PASSWORD=x \
  backend/.venv/Scripts/python -c "
import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from config.celery import app; print(app.send_task('rates.tasks.ingest_rates').id)"
```

A re-run reporting `landed=0 promoted=0` is the correct idempotent result.

---

## Environment variable reference

| Variable | web | worker | frontend | Value |
|---|:--:|:--:|:--:|---|
| `DJANGO_SECRET_KEY` | ✓ | ✓ | | long random string |
| `DJANGO_DEBUG` | ✓ | ✓ | | `false` |
| `DJANGO_ALLOWED_HOSTS` | ✓ | ✓ | | web: `${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app`; worker: `*` |
| `INGEST_API_TOKEN` | ✓ | ✓ | | long random string |
| `DATABASE_URL` | ✓ | ✓ | | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | ✓ | ✓ | | `${{Redis.REDIS_URL}}` |
| `CORS_ALLOWED_ORIGINS` | ✓ | | | frontend URL |
| `SEED_SINCE` | ✓ | ✓ | | `2026-03-01` |
| `RUN_MIGRATIONS` | `true` | `false` | | migrate on boot (web only) |
| `PORT` | `8000` | | `3000` | must match the domain's target port |
| `INGEST_BATCH_SIZE` | | `5000` | | caps peak ingest memory |
| `NEXT_PUBLIC_API_URL` | | | ✓ | web URL (**build-time**) |

Optional: `INGEST_INTERVAL_SECONDS` (beat cadence, default 3600),
`RATE_OUTLIER_CEILING`, `SLOW_QUERY_SECONDS` — all in [`.env.example`](.env.example).

---

## Free-plan limits, and what each one forces

| Limit | Consequence |
|---|---|
| 5 resources per project | `beat` merged into `worker` (`celery worker --beat`) |
| 500 MB per volume | seed bounded to `--since 2026-03-01`; a larger window kills Postgres |
| 1 GB memory per service | `--concurrency=1` and `INGEST_BATCH_SIZE=5000` to avoid OOM |

## Notes & gotchas

- **Custom start command replaces `ENTRYPOINT`** → invoke `/app/entrypoint.sh`
  explicitly, or migrations never run.
- **`railway redeploy` won't pick up changed service settings** → use `railway up`.
- **Domain target port must match the bound port** → pin `PORT`, or get a 502 on a
  green deploy.
- **`healthcheck.railway.app` must be in `ALLOWED_HOSTS`** → or healthchecks 400.
- **The 33 MB parquet is uploaded on every `railway up`** → occasional HTTP 500s from
  the upload endpoint; retrying works.
- **Deleting a database service drops the reference variables** that pointed at it
  (`DATABASE_URL` on web/worker) — re-set them after recreating it.
- **Bring it down** by deleting the project (or pausing services) to stop billing.
