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

# Hosts without a shell (Render free tier) cannot run the demo seed by hand.
# Idempotent: skips organizations that already exist. Requires DEMO_PASSWORD so
# no generated password ends up in platform logs.
if [ "${SEED_DEMO_ON_START:-false}" = "true" ]; then
  if [ -n "${DEMO_PASSWORD:-}" ]; then
    echo "Seeding demo organizations (if missing)..."
    python -m app.scripts.seed_demo
  else
    echo "SEED_DEMO_ON_START=true but DEMO_PASSWORD is empty; skipping demo seed." >&2
  fi
fi

# Prometheus multi-process mode: every API worker process writes its metrics
# to this directory and one /metrics scrape aggregates them. Cleared on start
# so a restart does not resurrect stale counters.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

exec "$@"
