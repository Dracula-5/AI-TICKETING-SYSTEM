#!/bin/sh
set -e

# Start-up tasks, in one Python process (app/scripts/prestart.py):
# * MIGRATE_ON_START (default true): `alembic upgrade head`. Development compose
#   migrates on start for convenience. Production runs a dedicated one-shot
#   `migrate` service first and sets MIGRATE_ON_START=false on the API and
#   worker, so a deploy migrates exactly once (and a failed migration stops the
#   rollout before new code starts).
# * PLATFORM_ADMIN_EMAIL + PLATFORM_ADMIN_PASSWORD: create the platform administrator.
# (SEED_DEMO_ON_START is handled by the API itself, in the background after start-up.)
if [ "${MIGRATE_ON_START:-true}" = "true" ] || [ -n "${PLATFORM_ADMIN_EMAIL:-}" ]; then
  python -m app.scripts.prestart
fi

# Prometheus multi-process mode: every API worker process writes its metrics
# to this directory and one /metrics scrape aggregates them. Cleared on start
# so a restart does not resurrect stale counters.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

exec "$@"
