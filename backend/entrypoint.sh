#!/bin/sh
# Backend container entrypoint: wait for Postgres, apply migrations, then run CMD.
# Migrations run only in the web service (see docker-compose) so workers don't race.
set -e

# Managed hosts (Railway, Neon, …) inject a single DATABASE_URL and no discrete
# POSTGRES_* vars; local compose sets the discrete ones. Settings already prefer
# DATABASE_URL, so the wait target has to follow the same precedence — otherwise
# this loops forever on the compose-only default host "db".
if [ -n "${DATABASE_URL}" ]; then
  # postgresql://user:pass@host:port/db?args -> host:port
  # Strip to the LAST "@" so passwords containing "@" don't truncate the host.
  _hostport="${DATABASE_URL##*@}"
  _hostport="${_hostport%%/*}"   # drop /dbname and any ?query after it
  DB_HOST="${_hostport%%:*}"
  DB_PORT="${_hostport##*:}"
  if [ "${DB_PORT}" = "${DB_HOST}" ]; then
    DB_PORT=5432   # URL carried no explicit port
  fi
else
  DB_HOST="${POSTGRES_HOST:-db}"
  DB_PORT="${POSTGRES_PORT:-5432}"
fi

echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT}..."
until nc -z "${DB_HOST}" "${DB_PORT}"; do
  sleep 1
done
echo "Postgres is up."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
fi

exec "$@"
