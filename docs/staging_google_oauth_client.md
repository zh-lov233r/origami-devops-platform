<!-- 中文：staging Google OAuth Client 准备清单。 -->
<!-- English: Staging Google OAuth Client preparation checklist. -->

# Staging Google OAuth Client

Use a dedicated Google OAuth client for staging. Do not reuse the production
OAuth client, because redirect URI and access policy changes should be tested in
staging before production.

## Inputs

Fill these values before creating the client:

- Staging host: `origami-staging.internal`
- Authorized JavaScript origin: `https://origami-staging.internal`
- Authorized redirect URI: `https://origami-staging.internal/oauth2/callback`
- OAuth client type: Web application
- OAuth scopes used by oauth2-proxy: `openid email profile`
- Temporary allowlist mode: `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE`
- Later Workspace mode: value for `GOOGLE_WORKSPACE_DOMAIN`
- Secret destination: staging secrets store entry for `.env.staging`

## Google Cloud Steps

1. Open the Google Cloud project that owns internal developer tooling.
2. Confirm the OAuth consent configuration is internal to the company Workspace
   when possible.
3. Create a new OAuth client of type `Web application`.
4. Name it `Origami Staging SSO`.
5. Add `https://origami-staging.internal` as the authorized JavaScript origin.
6. Add `https://origami-staging.internal/oauth2/callback` as the authorized
   redirect URI.
7. Save the generated client ID and client secret into the staging secrets store.
8. Put those values into `.env.staging` as `OAUTH2_PROXY_CLIENT_ID` and
   `OAUTH2_PROXY_CLIENT_SECRET`.
9. For the first staging pass, keep `GOOGLE_WORKSPACE_DOMAIN` empty and set
   `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE=/etc/oauth2-proxy/authenticated-emails.txt`.
10. Copy `configs/auth/oauth2-proxy/authenticated-emails.txt.example` to
   `configs/auth/oauth2-proxy/authenticated-emails.txt` on the staging host and
   keep `ziyue.ingen@gmail.com` as the temporary allowed Gmail account.
11. If Google Workspace app access controls are enforced later, allow this OAuth
   client for the company Workspace domain or the Carry & Go developer group.

Google's OAuth client documentation notes that the redirect URI sent by the app
must match an authorized redirect URI on the OAuth client, otherwise Google
returns a `redirect_uri_mismatch` error. Keep the staging callback exactly in
sync with `OAUTH2_PROXY_REDIRECT_URL`.

Official references:

- https://support.google.com/cloud/answer/6158849
- https://developers.google.com/identity/protocols/oauth2/web-server

## Local Secret Material

Generate staging-only secrets on a trusted machine:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

Use the first value for `ORIGAMI_API_TOKEN`. Use the second value for
`OAUTH2_PROXY_COOKIE_SECRET`.

## Preflight

After `.env.staging` is filled on the staging host:

```bash
ORIGAMI_STAGING_HOSTNAME=origami-staging.internal \
scripts/staging_host_preflight.sh
```

The preflight checks that the host can run Docker Compose, required env keys are
present, placeholder secrets have been replaced, and staging OAuth URLs match the
expected host.

## Acceptance

The OAuth client is ready when:

- `scripts/staging_host_preflight.sh` passes on the staging host.
- `scripts/staging_sso_smoke.sh` confirms `/oauth2/start` redirects to Google.
- Browser login succeeds for `ziyue.ingen@gmail.com`, the temporary Gmail
  allowlisted in `configs/auth/oauth2-proxy/authenticated-emails.txt`.
- Browser login fails for any account not in that allowlist.
- oauth2-proxy logs show the expected email and no redirect mismatch.
