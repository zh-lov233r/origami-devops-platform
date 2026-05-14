#!/usr/bin/env bash
# 中文：真实 staging 主机预检，验证 Docker、compose 配置、端口和 staging secret 占位符。
# English: Real staging host preflight for Docker, compose config, ports, and staging secret placeholders.

set -euo pipefail

env_file="${ORIGAMI_STAGING_ENV_FILE:-.env.staging}"
expected_host="${ORIGAMI_STAGING_HOSTNAME:-origami-staging.internal}"
required_commands=(curl docker openssl)
compose_args=(--env-file "${env_file}" -f docker-compose.prod.yml -f docker-compose.sso.yml)
required_env_keys=(
  ORIGAMI_ENV
  ORIGAMI_API_IMAGE
  ORIGAMI_API_TOKEN
  ORIGAMI_ALLOWED_ORIGINS
  ORIGAMI_TRUSTED_HOSTS
  ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED
  ORIGAMI_GRAFANA_URL
  GRAFANA_ROOT_URL
  GRAFANA_ADMIN_USER
  GRAFANA_ADMIN_PASSWORD
  ORIGAMI_SSO_BIND
  OAUTH2_PROXY_CLIENT_ID
  OAUTH2_PROXY_CLIENT_SECRET
  OAUTH2_PROXY_COOKIE_SECRET
  OAUTH2_PROXY_REDIRECT_URL
  OAUTH2_PROXY_COOKIE_DOMAINS
  OAUTH2_PROXY_WHITELIST_DOMAINS
  GOOGLE_WORKSPACE_DOMAIN
  OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE
  ORIGAMI_STAGING_BASE_URL
)

fail() {
  echo "Staging host preflight failed: $*" >&2
  exit 1
}

pass() {
  echo "ok - $*"
}

env_value() {
  key="$1"
  grep -E "^${key}=" "${env_file}" | tail -n 1 | cut -d= -f2-
}

check_not_placeholder() {
  key="$1"
  value="$(env_value "${key}")"

  if [ -z "${value}" ]; then
    fail "${key} is empty in ${env_file}"
  fi

  case "${value}" in
    replace-with-* | yourcompany.com)
      fail "${key} still uses placeholder value '${value}' in ${env_file}"
      ;;
  esac
}

check_host_reference() {
  key="$1"
  value="$(env_value "${key}")"

  case "${value}" in
    *"${expected_host}"*) ;;
    *)
      fail "${key}='${value}' does not reference expected host '${expected_host}'"
      ;;
  esac
}

if [ ! -f "${env_file}" ]; then
  fail "missing ${env_file}; copy .env.staging.example and fill staging values first"
fi
pass "found ${env_file}"

for command_name in "${required_commands[@]}"; do
  command -v "${command_name}" >/dev/null 2>&1 || fail "missing required command: ${command_name}"
done
pass "required commands are installed"

docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available"
pass "Docker Compose v2 is available"

docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable by this user"
pass "Docker daemon is reachable"

for key in "${required_env_keys[@]}"; do
  if ! grep -qE "^${key}=" "${env_file}"; then
    fail "${key} is missing from ${env_file}"
  fi
done
pass "required staging env keys are present"

if [ "$(env_value ORIGAMI_ENV)" != "staging" ]; then
  fail "ORIGAMI_ENV must be staging"
fi
pass "ORIGAMI_ENV is staging"

check_not_placeholder ORIGAMI_API_TOKEN
check_not_placeholder GRAFANA_ADMIN_PASSWORD
check_not_placeholder OAUTH2_PROXY_CLIENT_ID
check_not_placeholder OAUTH2_PROXY_CLIENT_SECRET
check_not_placeholder OAUTH2_PROXY_COOKIE_SECRET

workspace_domain="$(env_value GOOGLE_WORKSPACE_DOMAIN)"
authenticated_emails_file="$(env_value OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE)"

if [ -z "${workspace_domain}" ] && [ -z "${authenticated_emails_file}" ]; then
  fail "set either GOOGLE_WORKSPACE_DOMAIN or OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE"
fi

if [ -n "${workspace_domain}" ]; then
  check_not_placeholder GOOGLE_WORKSPACE_DOMAIN
fi

if [ -n "${authenticated_emails_file}" ]; then
  if [ "${authenticated_emails_file}" != "/etc/oauth2-proxy/authenticated-emails.txt" ]; then
    fail "OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE must be /etc/oauth2-proxy/authenticated-emails.txt"
  fi

  local_email_file="configs/auth/oauth2-proxy/authenticated-emails.txt"
  if [ ! -f "${local_email_file}" ]; then
    fail "missing ${local_email_file}; copy configs/auth/oauth2-proxy/authenticated-emails.txt.example and fill the allowed Gmail address"
  fi

  if grep -Eq 'your-staging-account@gmail.com|replace-with|example.com' "${local_email_file}"; then
    fail "${local_email_file} still contains placeholder email values"
  fi

  if ! grep -Eq '^[^[:space:]#]+@[^[:space:]#]+\.[^[:space:]#]+$' "${local_email_file}"; then
    fail "${local_email_file} must contain at least one email address"
  fi
fi
pass "required secret-like values and OAuth allowlist are not placeholders"

check_host_reference ORIGAMI_ALLOWED_ORIGINS
check_host_reference ORIGAMI_GRAFANA_URL
check_host_reference GRAFANA_ROOT_URL
check_host_reference OAUTH2_PROXY_REDIRECT_URL
check_host_reference OAUTH2_PROXY_COOKIE_DOMAINS
check_host_reference OAUTH2_PROXY_WHITELIST_DOMAINS
check_host_reference ORIGAMI_STAGING_BASE_URL
pass "staging host references are consistent"

case "$(env_value ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED)" in
  true) pass "trusted proxy auth is required" ;;
  *) fail "ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED must be true" ;;
esac

case "$(env_value OAUTH2_PROXY_REDIRECT_URL)" in
  "https://${expected_host}/oauth2/callback") pass "OAuth redirect URI matches staging host" ;;
  *) fail "OAUTH2_PROXY_REDIRECT_URL must be https://${expected_host}/oauth2/callback" ;;
esac

cookie_secret="$(env_value OAUTH2_PROXY_COOKIE_SECRET)"
if [ "${#cookie_secret}" -lt 32 ]; then
  fail "OAUTH2_PROXY_COOKIE_SECRET should be at least 32 characters"
fi
pass "OAuth cookie secret length looks acceptable"

docker compose "${compose_args[@]}" config >/dev/null
pass "staging compose config renders"

if [ -n "$(docker ps --filter publish=8000 --format '{{.Names}}')" ]; then
  fail "host port 8000 is already published by a running container"
fi

if [ -n "$(docker ps --filter publish=8080 --format '{{.Names}}')" ]; then
  fail "host port 8080 is already published by a running container"
fi
pass "default API and SSO bind ports are not already published by Docker"

echo "Staging host preflight passed."
