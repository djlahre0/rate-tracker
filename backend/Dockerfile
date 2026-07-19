# Python 3.13 (not 3.14; Celery 5.6 only has initial 3.14 support).
#
# NOTE: this builds from the *repo root* as context, not backend/ — the image has
# to carry data/rates_seed.parquet so the Celery-scheduled ingest works on hosts
# with no volume mount (Railway). Build it as:
#   docker build -f backend/Dockerfile .
# docker-compose.yml and the root railway.json are both set up this way already.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: libpq for psycopg, netcat for the entrypoint's DB wait.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Seed parquet at /data — the path settings resolve (BASE_DIR.parent/"data").
# Compose still bind-mounts ./data over this for fast local iteration; baking it
# in is what makes the hourly ingest_rates task real on a mountless host.
COPY data/ /data/

RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
