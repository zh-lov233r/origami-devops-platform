<!-- 中文：真实 staging 部署准备包，覆盖环境变量、SSO、验证、日志和回滚。 -->
<!-- English: Real staging deployment package covering env vars, SSO, validation, logs, and rollback. -->

# Staging Deployment

Use this runbook to bring up the internal staging instance before opening the
platform to Carry & Go developers. Staging should match production security
boundaries while using staging-only secrets, OAuth clients, and retained data.

## Scope

Staging validates the internal developer platform only:

- PIC 2.0 pipeline, Carry & Go scenarios, benchmark, audit, dashboard, and
  observability workflows.
- Google Workspace SSO through oauth2-proxy and Nginx.
- Per-user scenario/config storage under `artifacts/users/<user_id>/`.
- No real robot control, no production robot command path, and no customer data.

## Prerequisites

- Internal DNS name such as `origami-staging.internal`.
- TLS terminates before `ORIGAMI_SSO_BIND`, or the host is reachable only through
  the approved internal network/VPN.
- Docker with Compose v2 on the staging host.
- Access to the GitHub Container Registry image built by `release-gate`, or a
  local build path from this repository.
- Staging-only Google OAuth web client.
- A staging secrets store entry for `.env.staging`; do not commit real secrets.

## Google OAuth Client

Create a Google OAuth web application for staging:

- Authorized JavaScript origin: `https://origami-staging.internal`
- Authorized redirect URI: `https://origami-staging.internal/oauth2/callback`

Use the company Google Workspace domain in `GOOGLE_WORKSPACE_DOMAIN`. Keep
staging and production OAuth clients separate so callback changes can be tested
without touching production login.

## Environment

Start from the template:

```bash
cp .env.staging.example .env.staging
```

Fill these values before starting the stack:

- `ORIGAMI_API_IMAGE`: image tag or digest from the green `release-gate` run.
- `ORIGAMI_API_TOKEN`: strong staging-only internal proxy token.
- `GRAFANA_ADMIN_PASSWORD`: staging-only Grafana admin password.
- `OAUTH2_PROXY_CLIENT_ID` and `OAUTH2_PROXY_CLIENT_SECRET`: staging Google OAuth
  client credentials.
- `OAUTH2_PROXY_COOKIE_SECRET`: 32-byte base64-url random secret.
- `GOOGLE_WORKSPACE_DOMAIN`: allowed company Gmail / Workspace domain.

Generate the cookie secret with:

```bash
python -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

## Deploy

Run from the repository checkout on the staging host:

```bash
docker compose \
  --env-file .env.staging \
  -f docker-compose.prod.yml \
  -f docker-compose.sso.yml \
  up -d --build
```

If the staging host pulls a previously built image, set `ORIGAMI_API_IMAGE` in
`.env.staging` and omit `--build`.

Check service state:

```bash
docker compose \
  --env-file .env.staging \
  -f docker-compose.prod.yml \
  -f docker-compose.sso.yml \
  ps
```

## Automated Smoke

Run the staging SSO smoke check from a network location that can reach the
staging hostname:

```bash
ORIGAMI_STAGING_BASE_URL=https://origami-staging.internal \
scripts/staging_sso_smoke.sh
```

When running from the staging host or an approved VPN path, include the direct
API URL and token to verify that token-only API access is rejected:

```bash
ORIGAMI_STAGING_BASE_URL=https://origami-staging.internal \
ORIGAMI_STAGING_DIRECT_API_URL=http://127.0.0.1:8000 \
ORIGAMI_API_TOKEN=<staging internal token> \
scripts/staging_sso_smoke.sh
```

The smoke script verifies:

- `/api/health` returns 200 through the SSO proxy.
- `/dashboard` redirects unauthenticated users to oauth2-proxy.
- `/api/scenarios` redirects unauthenticated browser traffic to oauth2-proxy.
- `/oauth2/start` redirects to Google OAuth.
- Optional direct API check returns 401 or is network-blocked.

## Manual Acceptance

After automated smoke passes, complete these checks in a browser:

- Visit `https://origami-staging.internal/dashboard`.
- Confirm Google login is required.
- Confirm a company Gmail / Workspace account can log in.
- Confirm a non-company account cannot log in.
- Create a custom scenario and run it.
- Confirm the scenario appears only for that signed-in user.
- Open `/grafana/` and confirm the overview dashboard loads.
- Confirm Prometheus has recent API scrape data.

## Logs

Useful staging diagnostics:

```bash
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 api
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 sso-proxy
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 oauth2-proxy
```

Request failures should include request ids in API logs. SSO failures usually
belong to `oauth2-proxy` when the Google OAuth client, redirect URI, cookie
domain, or allowed Workspace domain is wrong.

## Rollback

Rollback target: the previous green image tag or digest from `release-gate`.

```bash
ORIGAMI_API_IMAGE=<previous-image-ref> \
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml up -d api
```

Rollback is complete only after:

- `scripts/staging_sso_smoke.sh` passes.
- A browser login still works for a company account.
- Existing staging artifacts and user scenarios remain visible.

## Backup Notes

Before inviting developers, define a backup location for:

- `origami-artifacts` volume: user scenarios, run artifacts, audit bundles.
- `grafana-data` volume: staging dashboard state.
- `prometheus-data` volume: short-term metrics history.

For v0.1 staging, a daily volume snapshot is enough if the retention window and
restore owner are documented.
