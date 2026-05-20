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
- Staging-only Google OAuth web client. The first staging pass uses a single
  Gmail account allowlist rather than allowing the whole `gmail.com` domain.
- A staging secrets store entry for `.env.staging`; do not commit real secrets.

Run host preflight after `.env.staging` is filled:

```bash
ORIGAMI_STAGING_HOSTNAME=origami-staging.internal \
scripts/staging_host_preflight.sh
```

## Google OAuth Client

Create a Google OAuth web application for staging:

- Authorized JavaScript origin: `https://origami-staging.internal`
- Authorized redirect URI: `https://origami-staging.internal/oauth2/callback`

For the first staging pass, keep `GOOGLE_WORKSPACE_DOMAIN` empty and use
`OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE=/etc/oauth2-proxy/authenticated-emails.txt`.
This authorizes only the email addresses listed in
`configs/auth/oauth2-proxy/authenticated-emails.txt` on the staging host. Do not
set `GOOGLE_WORKSPACE_DOMAIN=gmail.com`, because that would allow any Gmail
account.

Later, when the company Workspace domain is ready, set `GOOGLE_WORKSPACE_DOMAIN`
to that domain and clear `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE`.

Follow `docs/staging_google_oauth_client.md` for the Google Cloud checklist.

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
- `GOOGLE_WORKSPACE_DOMAIN`: leave empty for temporary single-Gmail staging.
- `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE`: set to
  `/etc/oauth2-proxy/authenticated-emails.txt` for temporary single-Gmail
  staging.

Create the local staging email allowlist:

```bash
cp configs/auth/oauth2-proxy/authenticated-emails.txt.example \
  configs/auth/oauth2-proxy/authenticated-emails.txt
```

Edit `configs/auth/oauth2-proxy/authenticated-emails.txt` and put the temporary
allowed Gmail account there. The committed example allowlists
`ziyue.ingen@gmail.com` for the first staging pass. The copied
`authenticated-emails.txt` file is ignored by git.

Generate the cookie secret with:

```bash
python -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

Generate the internal API token with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

After secrets are filled, run:

```bash
make staging-host-preflight
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
- Confirm the Gmail account listed in
  `configs/auth/oauth2-proxy/authenticated-emails.txt` can log in.
- Confirm any account not listed in that allowlist cannot log in.
- Create a custom scenario and run it.
- Confirm the scenario appears only for that signed-in user.
- Open `/grafana/` and confirm the overview dashboard loads.
- Confirm Prometheus has recent API scrape data.

## Acceptance Report

Record the staging evidence with the acceptance report generator. Start with a
pending report before the rehearsal:

```bash
make staging-acceptance-report
```

As checks pass, attach status and evidence:

```bash
scripts/write_staging_acceptance_report.py \
  --base-url https://origami-staging.internal \
  --image-ref <image-ref-or-digest> \
  --git-sha <git-sha> \
  --owner <restore-and-release-owner> \
  --status sso_smoke=pass \
  --evidence sso_smoke="scripts/staging_sso_smoke.sh passed from VPN" \
  --status structured_logs=pass \
  --evidence structured_logs="validate_structured_logs.py --require-run-id passed"
```

The generator writes Markdown and JSON under `artifacts/acceptance/`. Keep the
final report with the release notes. The report should remain `pending` until
manual browser login, user isolation, observability, structured logging,
backup/restore, rollback, and runbook rehearsal evidence is attached.

## Logs

Useful staging diagnostics:

```bash
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 api
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 sso-proxy
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml logs --tail=120 oauth2-proxy
```

Request failures should include request ids in API logs, and run-triggering
operations should include run ids. Use `docs/structured_logging.md` and
`scripts/validate_structured_logs.py --require-run-id` to validate the API log
field contract during staging rehearsal.

SSO failures usually belong to `oauth2-proxy` when the Google OAuth client,
redirect URI, cookie domain, or allowed Workspace domain is wrong.

## Rollback

Rollback target: the previous green image tag or digest from `release-gate`.

```bash
ORIGAMI_API_IMAGE=<previous-image-ref> \
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml up -d api
```

Rollback is complete only after:

- `scripts/staging_sso_smoke.sh` passes.
- A browser login still works for the allowlisted staging Gmail account.
- Existing staging artifacts and user scenarios remain visible.

## Backup Notes

Before inviting developers, define and rehearse the backup location for:

- `origami-artifacts` volume: user scenarios, run artifacts, audit bundles.
- `grafana-data` volume: staging dashboard state.
- `prometheus-data` volume: short-term metrics history.

For the Origami artifact volume, use `scripts/artifact_backup.sh` and
`scripts/artifact_restore.sh`. The detailed restore rehearsal and production
restore checklist lives in `docs/artifact_backup_restore.md`.

For v0.1 staging, a daily artifact backup or volume snapshot is enough if the
retention window, restore owner, and latest restore rehearsal result are
documented.
