#!/usr/bin/env bash
# Restore PostgreSQL from a backup produced by backup.sh. DESTRUCTIVE: replaces
# the current database contents. Stops the API and worker while restoring.
#   ./deploy/restore.sh backups/<file>.dump
set -euo pipefail
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
DUMP=${1:?usage: restore.sh <file.dump>}
[ -f "$DUMP" ] || { echo "no such file: $DUMP"; exit 1; }
read -r -p "Replace the current database with $DUMP? Type 'restore' to continue: " answer
[ "$answer" = "restore" ] || { echo "aborted"; exit 1; }
# Read one KEY from .env without executing it as shell (values may contain spaces).
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//'; }
PGUSER_=$(envval POSTGRES_USER); PGUSER_=${PGUSER_:-nexadesk}
PGDB_=$(envval POSTGRES_DB); PGDB_=${PGDB_:-nexadesk}
COMPOSE=(docker compose --env-file .env -f deploy/docker-compose.prod.yml)
export IMAGE_TAG=${IMAGE_TAG:-$(cat .deployed_tag 2>/dev/null || echo current)}

"${COMPOSE[@]}" stop backend worker
"${COMPOSE[@]}" exec -T postgres pg_restore --clean --if-exists --no-owner \
  -U "$PGUSER_" -d "$PGDB_" < "$DUMP"
"${COMPOSE[@]}" up -d backend worker
echo "restored from $DUMP"
