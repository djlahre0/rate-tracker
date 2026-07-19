#!/bin/sh
# Backend container entrypoint: wait for Postgres, apply migrations, then run CMD.
# Migrations run only in the web service (see docker-compose) so workers don't race.
set -e

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_PORT:=5432}"

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until nc -z "${POSTGRES_HOST}" "${POSTGRES_PORT}"; do
  sleep 1
done
echo "Postgres is up."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput
fi

exec "$@"
