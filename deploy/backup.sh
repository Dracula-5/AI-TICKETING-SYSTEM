#!/usr/bin/env bash
# Logical backup of PostgreSQL (custom format, restorable with deploy/restore.sh)
# plus a tarball of the attachments volume. Keeps 14 days of backups.
#   ./deploy/backup.sh [label]
set -euo pipefail
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
LABEL=${1:-manual}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=backups
mkdir -p "$OUT"

# Read one KEY from .env without executing it as shell (values may contain spaces).
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//'; }
PGUSER_=$(envval POSTGRES_USER); PGUSER_=${PGUSER_:-nexadesk}
PGDB_=$(envval POSTGRES_DB); PGDB_=${PGDB_:-nexadesk}
# Compose needs IMAGE_TAG to parse the file, even for `exec`.
export IMAGE_TAG=${IMAGE_TAG:-$(cat .deployed_tag 2>/dev/null || echo current)}

# Write to a temp file and move into place only on success, so a failed dump
# can never leave an empty file that looks like a backup.
TMP="$OUT/.$LABEL-$STAMP.dump.partial"
trap 'rm -f "$TMP"' EXIT
docker compose --env-file .env -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$PGUSER_" -d "$PGDB_" -Fc > "$TMP"
[ -s "$TMP" ] || { echo "pg_dump produced no data"; exit 1; }
mv "$TMP" "$OUT/$LABEL-$STAMP.dump"

# MSYS_NO_PATHCONV: keeps Git Bash (Windows rehearsals) from rewriting container paths; no-op on Linux.
MSYS_NO_PATHCONV=1 docker run --rm -v nexadesk_attachments:/data:ro -v "$APP_DIR/$OUT":/backup alpine \
  tar czf "/backup/$LABEL-$STAMP-attachments.tgz" -C /data .

# Pre-deploy backups are also referenced by tag for restore.sh.
case "$LABEL" in pre-deploy-*) cp "$OUT/$LABEL-$STAMP.dump" "$OUT/$LABEL.dump" ;; esac

find "$OUT" -type f -mtime +14 \( -name '*.dump' -o -name '*.tgz' \) -delete
echo "backup written: $OUT/$LABEL-$STAMP.dump ($(du -h "$OUT/$LABEL-$STAMP.dump" | cut -f1))"
# Off-site copy (recommended): e.g. `rclone copy backups remote:nexadesk-backups`
