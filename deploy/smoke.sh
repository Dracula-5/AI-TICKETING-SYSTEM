#!/usr/bin/env bash
# Post-deploy smoke test: readiness (DB reachable + schema at migration head),
# the SPA, the API docs, and an authenticated endpoint rejecting anonymous
# calls — all through the proxy. The whole sequence is retried while
# containers (and the proxy's upstream health checks) settle.
set -uo pipefail
DOMAIN=${1:?usage: smoke.sh <domain>}
BASE="https://$DOMAIN"
TLS=()
[ "$DOMAIN" = "localhost" ] && TLS=(-k)   # Caddy's internal CA for local tests

check() {
  local ready code
  ready=$(curl -fsS --max-time 10 "${TLS[@]}" "$BASE/ready") || return 1
  echo "$ready" | grep -q '"status":"ready"' || return 1
  curl -fsS --max-time 10 "${TLS[@]}" -o /dev/null "$BASE/" || return 1
  curl -fsS --max-time 10 "${TLS[@]}" -o /dev/null "$BASE/api/docs" || return 1
  code=$(curl -s --max-time 10 "${TLS[@]}" -o /dev/null -w '%{http_code}' "$BASE/api/v1/auth/me")
  [ "$code" = "401" ] || return 1
  echo "smoke ok: $ready"
}

for _ in $(seq 1 30); do
  check 2>/dev/null && exit 0
  sleep 5
done
echo "smoke failed: $BASE did not pass readiness/SPA/API checks within 150s"
exit 1
