#!/bin/sh

set -eu

max_attempts="${AURA_MIGRATION_MAX_ATTEMPTS:-30}"
sleep_seconds="${AURA_MIGRATION_RETRY_SLEEP_S:-2}"
attempt=1

while ! alembic upgrade head; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "API migration failed after ${attempt} attempts" >&2
    exit 1
  fi
  echo "API migration attempt ${attempt} failed, retrying in ${sleep_seconds}s..." >&2
  attempt=$((attempt + 1))
  sleep "$sleep_seconds"
done

exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
