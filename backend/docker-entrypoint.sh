#!/bin/sh
set -e

# Development compose migrates on start for convenience. Production runs a
# dedicated one-shot `migrate` service first and sets MIGRATE_ON_START=false
# on the API and worker, so a deploy migrates exactly once (and a failed
# migration stops the rollout before new code starts).
if [ "${MIGRATE_ON_START:-true}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

# Prometheus multi-process mode: every API worker process writes its metrics
# to this directory and one /metrics scrape aggregates them. Cleared on start
# so a restart does not resurrect stale counters.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

exec "$@"
