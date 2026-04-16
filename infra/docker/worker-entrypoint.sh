#!/bin/sh

set -eu

max_attempts="${AURA_API_WAIT_MAX_ATTEMPTS:-60}"
sleep_seconds="${AURA_API_WAIT_SLEEP_S:-2}"
attempt=1

while ! python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://api:8000/api/v1/ready', timeout=5).status == 200 else 1)"; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "Worker timed out waiting for API readiness after ${attempt} attempts" >&2
    exit 1
  fi
  echo "Worker waiting for API readiness (attempt ${attempt})..." >&2
  attempt=$((attempt + 1))
  sleep "$sleep_seconds"
done

exec arq apps.worker.worker_settings.WorkerSettings
