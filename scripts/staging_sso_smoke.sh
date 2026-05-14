#!/usr/bin/env bash
# 中文：真实 staging SSO smoke check，验证公开入口、OAuth 跳转和直连 API 边界。
# English: Real staging SSO smoke check for public ingress, OAuth redirects, and direct API boundaries.

set -euo pipefail

base_url="${ORIGAMI_STAGING_BASE_URL:?Set ORIGAMI_STAGING_BASE_URL, for example https://origami-staging.internal}"
direct_api_url="${ORIGAMI_STAGING_DIRECT_API_URL:-}"
api_token="${ORIGAMI_API_TOKEN:-}"
timeout_seconds="${ORIGAMI_STAGING_SMOKE_TIMEOUT_SECONDS:-60}"

base_url="${base_url%/}"
direct_api_url="${direct_api_url%/}"

fail() {
  echo "Staging SSO smoke failed: $*" >&2
  exit 1
}

curl_request() {
  if [ "${ORIGAMI_STAGING_INSECURE_TLS:-false}" = "true" ]; then
    curl -k "$@"
  else
    curl "$@"
  fi
}

http_code() {
  curl_request -sS -o /dev/null -w "%{http_code}" "$@" || true
}

headers_for() {
  curl_request -sS -D - -o /dev/null "$@"
}

header_status() {
  awk 'NR == 1 { print $2 }'
}

header_location() {
  awk 'tolower($1) == "location:" { print $2; exit }' | tr -d '\r'
}

health_ready=false
for _ in $(seq 1 "${timeout_seconds}"); do
  if [ "$(http_code "${base_url}/api/health")" = "200" ]; then
    health_ready=true
    break
  fi
  sleep 1
done

if [ "${health_ready}" != "true" ]; then
  fail "expected ${base_url}/api/health to return 200 within ${timeout_seconds}s"
fi

dashboard_headers="$(headers_for "${base_url}/dashboard")"
dashboard_status="$(printf '%s' "${dashboard_headers}" | header_status)"
dashboard_location="$(printf '%s' "${dashboard_headers}" | header_location)"

case "${dashboard_status}" in
  302 | 303) ;;
  *) fail "expected /dashboard to redirect unauthenticated users, got ${dashboard_status}" ;;
esac

case "${dashboard_location}" in
  *"/oauth2/start"*) ;;
  *) fail "expected /dashboard redirect to oauth2-proxy, got ${dashboard_location}" ;;
esac

scenario_headers="$(headers_for "${base_url}/api/scenarios")"
scenario_status="$(printf '%s' "${scenario_headers}" | header_status)"
scenario_location="$(printf '%s' "${scenario_headers}" | header_location)"

case "${scenario_status}" in
  302 | 303) ;;
  *) fail "expected /api/scenarios to redirect unauthenticated users, got ${scenario_status}" ;;
esac

case "${scenario_location}" in
  *"/oauth2/start"*) ;;
  *) fail "expected /api/scenarios redirect to oauth2-proxy, got ${scenario_location}" ;;
esac

oauth_headers="$(headers_for "${base_url}/oauth2/start?rd=${base_url}/dashboard")"
oauth_status="$(printf '%s' "${oauth_headers}" | header_status)"
oauth_location="$(printf '%s' "${oauth_headers}" | header_location)"

case "${oauth_status}" in
  302 | 303) ;;
  *) fail "expected /oauth2/start to redirect to Google OAuth, got ${oauth_status}" ;;
esac

case "${oauth_location}" in
  *"accounts.google.com"* | *"google.com"*) ;;
  *) fail "expected /oauth2/start redirect to Google OAuth, got ${oauth_location}" ;;
esac

if [ -n "${direct_api_url}" ]; then
  if [ -z "${api_token}" ]; then
    fail "ORIGAMI_API_TOKEN is required when ORIGAMI_STAGING_DIRECT_API_URL is set"
  fi

  direct_status="$(
    curl_request -sS -o /dev/null -w "%{http_code}" \
      -H "X-Origami-Token: ${api_token}" \
      "${direct_api_url}/api/scenarios" || true
  )"

  case "${direct_status}" in
    000 | 401) ;;
    *)
      fail "expected direct API token-only request to be blocked or 401, got ${direct_status}"
      ;;
  esac
fi

echo "Staging SSO smoke passed."
