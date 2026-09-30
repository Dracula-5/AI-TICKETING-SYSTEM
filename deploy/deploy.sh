#!/usr/bin/env bash
# Deploy an image tag (normally the git SHA CI built):  ./deploy/deploy.sh <tag>
#
# 1. back up the database (restore point for a schema change that must be undone)
# 2. pull images for <tag>
# 3. start the stack: the one-shot `migrate` service runs first; API and worker
#    start only if it succeeds
# 4. smoke-test through the proxy
# If step 3 or 4 fails, roll back to the previously deployed tag and exit 1.
# (DEPLOY_SKIP_GIT / DEPLOY_SKIP_PULL exist only for local rehearsals.)
set -euo pipefail

APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
TAG=${1:?usage: deploy.sh <image-tag>}
COMPOSE=(docker compose --env-file .env -f deploy/docker-compose.prod.yml)
DOMAIN=$(grep -E '^DOMAIN=' .env | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//')
PREVIOUS=$(cat .deployed_tag 2>/dev/null || echo "")

log() { printf '%s  %s\n' "$(date -u +%FT%TZ)" "$*"; }

log "Deploying $TAG (previous: ${PREVIOUS:-none})"
if [ "${DEPLOY_SKIP_GIT:-false}" != "true" ]; then
  git fetch --quiet origin && git checkout --quiet "$TAG" 2>/dev/null \
    || log "git checkout of $TAG skipped (using current compose files)"
fi

if docker volume inspect nexadesk_postgres_data >/dev/null 2>&1; then
  log "Pre-deploy backup"
  "$APP_DIR/deploy/backup.sh" "pre-deploy-$TAG"
fi

export IMAGE_TAG=$TAG
[ "${DEPLOY_SKIP_PULL:-false}" = "true" ] || "${COMPOSE[@]}" pull --quiet

if "${COMPOSE[@]}" up -d --remove-orphans && "$APP_DIR/deploy/smoke.sh" "$DOMAIN"; then
  echo "$PREVIOUS" > .previous_tag
  echo "$TAG" > .deployed_tag
  "${COMPOSE[@]}" ps
  log "Deployed $TAG"
  docker image prune -f --filter "until=168h" >/dev/null
  exit 0
fi

log "Deployment of $TAG FAILED"
"${COMPOSE[@]}" logs --no-color --tail 50 migrate backend worker || true
if [ -n "$PREVIOUS" ]; then
  log "Rolling back to $PREVIOUS"
  IMAGE_TAG=$PREVIOUS "${COMPOSE[@]}" up -d --remove-orphans
  "$APP_DIR/deploy/smoke.sh" "$DOMAIN" && log "Rolled back to $PREVIOUS"
fi
exit 1
