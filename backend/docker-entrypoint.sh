#!/bin/sh
set -e

# Start-up tasks, in one Python process (app/scripts/prestart.py):
# * MIGRATE_ON_START (default true): `alembic upgrade head`. Development compose
#   migrates on start for convenience. Production runs a dedicated one-shot
#   `migrate` service first and sets MIGRATE_ON_START=false on the API and
#   worker, so a deploy migrates exactly once (and a failed migration stops the
#   rollout before new code starts).
# * SEED_DEMO_ON_START (default false): create the demo organizations if
#   missing, for hosts without a shell (Render free tier). Needs DEMO_PASSWORD.
# * PLATFORM_ADMIN_EMAIL + PLATFORM_ADMIN_PASSWORD: create the platform administrator.
if [ "${MIGRATE_ON_START:-true}" = "true" ] || [ "${SEED_DEMO_ON_START:-false}" = "true" ] ||
  [ -n "${PLATFORM_ADMIN_EMAIL:-}" ]; then
  python -m app.scripts.prestart
fi

# Prometheus multi-process mode: every API worker process writes its metrics
# to this directory and one /metrics scrape aggregates them. Cleared on start
# so a restart does not resurrect stale counters.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

exec "$@"
