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

exec "$@"
