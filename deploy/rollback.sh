#!/usr/bin/env bash
# Roll back application code to the previously deployed image tag:
#   ./deploy/rollback.sh            # previous tag
#   ./deploy/rollback.sh <tag>      # a specific tag
#
# Code rollback only. Migrations are written expand/contract (new code works
# with the old schema and vice versa for one release), so rolling code back one
# release is safe without touching the database. If a release must also undo a
# schema change, restore the pre-deploy backup instead:
#   ./deploy/restore.sh backups/pre-deploy-<tag>.dump
set -euo pipefail
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
TARGET=${1:-$(cat .previous_tag 2>/dev/null || true)}
[ -n "$TARGET" ] || { echo "No previous tag recorded; pass one explicitly."; exit 1; }
CURRENT=$(cat .deployed_tag 2>/dev/null || echo "")
echo "Rolling back ${CURRENT:-?} -> $TARGET"
IMAGE_TAG=$TARGET docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d --remove-orphans backend worker web
DOMAIN=$(grep -E '^DOMAIN=' .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//')
"$APP_DIR/deploy/smoke.sh" "$DOMAIN"
echo "$CURRENT" > .previous_tag
echo "$TARGET" > .deployed_tag
echo "Rolled back to $TARGET"
