#!/usr/bin/env bash
# 中文：本地 SSO dry run smoke check，验证 oauth2-proxy/Nginx overlay、入口健康和用户隔离。
# English: Local SSO dry-run smoke check for the oauth2-proxy/Nginx overlay, ingress health, and user isolation.

set -euo pipefail

compose_env_file="${ORIGAMI_SSO_COMPOSE_ENV_FILE:-.env.production.example}"
compose_project="${ORIGAMI_SSO_COMPOSE_PROJECT:-origami-sso-dry-run}"
compose_args=(-p "${compose_project}" --env-file "${compose_env_file}" -f docker-compose.prod.yml -f docker-compose.sso.yml)
sso_base_url="${ORIGAMI_SSO_BASE_URL:-http://127.0.0.1:8080}"
api_base_url="${ORIGAMI_API_BASE_URL:-http://127.0.0.1:8000}"
trusted_actor="${ORIGAMI_SSO_DRY_RUN_ACTOR:-alice@example.com}"
python_bin="${PYTHON:-python3}"

export ORIGAMI_API_TOKEN="${ORIGAMI_API_TOKEN:-sso-dryrun-token}"
export ORIGAMI_ALLOWED_ORIGINS="${ORIGAMI_ALLOWED_ORIGINS:-http://127.0.0.1:8080}"
export ORIGAMI_TRUSTED_HOSTS="${ORIGAMI_TRUSTED_HOSTS:-127.0.0.1,localhost}"
export ORIGAMI_GRAFANA_URL="${ORIGAMI_GRAFANA_URL:-http://127.0.0.1:8080/grafana/d/origami-overview?orgId=1}"
export GRAFANA_ROOT_URL="${GRAFANA_ROOT_URL:-http://127.0.0.1:8080/grafana}"
export ORIGAMI_SSO_BIND="${ORIGAMI_SSO_BIND:-127.0.0.1:8080}"
export OAUTH2_PROXY_CLIENT_ID="${OAUTH2_PROXY_CLIENT_ID:-dry-run-client}"
export OAUTH2_PROXY_CLIENT_SECRET="${OAUTH2_PROXY_CLIENT_SECRET:-dry-run-secret}"
export OAUTH2_PROXY_COOKIE_SECRET="${OAUTH2_PROXY_COOKIE_SECRET:-0123456789abcdef0123456789abcdef}"
export OAUTH2_PROXY_REDIRECT_URL="${OAUTH2_PROXY_REDIRECT_URL:-http://127.0.0.1:8080/oauth2/callback}"
export OAUTH2_PROXY_COOKIE_DOMAINS="${OAUTH2_PROXY_COOKIE_DOMAINS:-127.0.0.1}"
export OAUTH2_PROXY_WHITELIST_DOMAINS="${OAUTH2_PROXY_WHITELIST_DOMAINS:-127.0.0.1}"
export GOOGLE_WORKSPACE_DOMAIN="${GOOGLE_WORKSPACE_DOMAIN:-example.com}"
export TRUSTED_ACTOR="${trusted_actor}"

show_diagnostics() {
  docker compose "${compose_args[@]}" ps >&2 || true
  docker compose "${compose_args[@]}" logs --no-color --tail=120 api oauth2-proxy sso-proxy >&2 || true
}

fail() {
  echo "SSO dry run failed: $*" >&2
  show_diagnostics
  exit 1
}

cleanup() {
  docker compose "${compose_args[@]}" down --volumes >/dev/null 2>&1 || true
}

trap cleanup EXIT

cleanup
docker compose "${compose_args[@]}" up -d --build

sso_ready=false
for _ in $(seq 1 60); do
  if curl -fsS "${sso_base_url}/api/health" >/dev/null 2>&1; then
    sso_ready=true
    break
  fi
  sleep 2
done

if [ "${sso_ready}" != "true" ]; then
  fail "SSO proxy did not become healthy at ${sso_base_url}/api/health"
fi

curl -fsS "${sso_base_url}/api/health" >/dev/null

dashboard_headers="$(curl -sS -D - -o /dev/null "${sso_base_url}/dashboard")"
dashboard_status="$(printf '%s' "${dashboard_headers}" | awk 'NR == 1 { print $2 }')"
dashboard_location="$(
  printf '%s' "${dashboard_headers}" \
    | awk 'tolower($1) == "location:" { print $2; exit }' \
    | tr -d '\r'
)"
expected_redirect="${sso_base_url}/oauth2/start?rd=${sso_base_url}/dashboard"

if [ "${dashboard_status}" != "302" ]; then
  fail "expected /dashboard to redirect unauthenticated users with 302, got ${dashboard_status}"
fi

case "${dashboard_location}" in
  "${expected_redirect}"*) ;;
  *)
    fail "expected /dashboard redirect to start with ${expected_redirect}, got ${dashboard_location}"
    ;;
esac

token_only_status="$(
  curl -sS -o /dev/null -w "%{http_code}" \
    -H "X-Origami-Token: ${ORIGAMI_API_TOKEN}" \
    "${api_base_url}/api/scenarios"
)"

if [ "${token_only_status}" != "401" ]; then
  fail "expected direct API token-only request to be rejected with 401, got ${token_only_status}"
fi

trusted_payload="$(
  curl -fsS \
    -H "X-Origami-Token: ${ORIGAMI_API_TOKEN}" \
    -H "X-Origami-Actor: ${trusted_actor}" \
    "${api_base_url}/api/scenarios"
)"

printf '%s' "${trusted_payload}" | "${python_bin}" -c '
import json
import os
import re
import sys

payload = json.load(sys.stdin)
actor = os.environ["TRUSTED_ACTOR"]
expected_user_id = re.sub(r"[^A-Za-z0-9._-]+", "-", actor).strip("-") or "anonymous"

assert payload["available"] is True, payload
assert payload["storage_scope"] == "user", payload
assert payload["owner_user_id"] == expected_user_id, payload
'

echo "SSO dry run smoke passed."
