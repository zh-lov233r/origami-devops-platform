<!-- 中文：Google Workspace SSO 部署说明，使用 oauth2-proxy 和 Nginx 将可信用户身份注入 Origami API。 -->
<!-- English: Google Workspace SSO deployment notes using oauth2-proxy and Nginx to inject trusted user identity into the Origami API. -->

# Google Workspace SSO

Origami supports a lightweight Google Workspace SSO deployment for internal
Carry & Go developers. Authentication stays at the edge proxy. The API receives
only a trusted identity header and an internal API token.

## Request Path

```text
Browser
  -> sso-proxy Nginx
  -> oauth2-proxy
  -> Google Workspace login
  -> sso-proxy injects X-Origami-Actor and X-Origami-Token
  -> Origami API
```

The API stores user-owned dashboard data under
`artifacts/users/<user_id>/` when `X-Origami-Actor` is present.

## Google OAuth Client

Create a Google OAuth web application for the internal host:

- Authorized JavaScript origin: `https://origami.internal`
- Authorized redirect URI: `https://origami.internal/oauth2/callback`

Save the client id and client secret into `.env.production`.

## Required Environment

Copy `.env.production.example` to `.env.production` and set:

```env
ORIGAMI_API_TOKEN=<strong internal proxy token>
ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED=true
ORIGAMI_ACTOR_HEADER=X-Origami-Actor

OAUTH2_PROXY_CLIENT_ID=<google oauth client id>
OAUTH2_PROXY_CLIENT_SECRET=<google oauth client secret>
OAUTH2_PROXY_COOKIE_SECRET=<32 byte base64-url secret>
OAUTH2_PROXY_REDIRECT_URL=https://origami.internal/oauth2/callback
OAUTH2_PROXY_COOKIE_DOMAINS=origami.internal
OAUTH2_PROXY_WHITELIST_DOMAINS=origami.internal
GOOGLE_WORKSPACE_DOMAIN=yourcompany.com
```

Generate the cookie secret with a cryptographically strong random value, for
example:

```bash
python -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

## Run

Start the production stack with the SSO overlay:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.sso.yml \
  up -d --build
```

Open `https://origami.internal` through the internal DNS / TLS endpoint that
routes to `ORIGAMI_SSO_BIND`.

## Dry Run

Run the local SSO smoke check before changing SSO deployment settings:

```bash
make sso-dry-run
```

The script starts `docker-compose.prod.yml` with `docker-compose.sso.yml` and
dummy OAuth credentials, then checks:

- `/api/health` is reachable through the SSO proxy.
- unauthenticated `/dashboard` traffic redirects to oauth2-proxy.
- direct API access with only `X-Origami-Token` is rejected.
- simulated trusted proxy identity headers activate per-user scenario storage.

## Security Notes

- Do not expose the API container directly to browsers.
- The Nginx proxy overwrites `X-Origami-Actor` and `X-Origami-Token`; client
  supplied identity headers are not trusted.
- `ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED=true` makes protected API routes reject
  token-only requests that do not include a trusted actor header.
- Prometheus `/metrics` can still be token-protected without requiring a user
  actor, so service monitoring does not need a human identity.

## Optional Group Restriction

Domain restriction is configured with `GOOGLE_WORKSPACE_DOMAIN`. If the company
wants to restrict access further to a Google Group such as
`carry-go-devs@yourcompany.com`, configure oauth2-proxy Google group support and
the Google Admin SDK delegation described by oauth2-proxy before enabling the
group requirement in production.
