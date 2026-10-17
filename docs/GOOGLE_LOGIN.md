# Google registration and login

## Current installation reference

- Google Cloud project ID: `lifegather-511910`.
- [LifeGather OAuth clients console](https://console.cloud.google.com/auth/clients?authuser=1&project=lifegather-511910&supportedpurview=project) — saved at the user's request on 2026-10-17. Requires signing in with an authorized Google account; `authuser=1` selects a browser account slot and may need adjusting in another browser.
- User reported local Google sign-in working on 2026-10-17. Client secrets remain only in ignored local configuration; do not copy them into this guide. Other self-hosted installations configure their own OAuth clients.

This slice implements Google OIDC authorization-code login with PKCE, a persistent private account identity, server-side sessions, and logout. It requests only `openid email profile`; it does not read Gmail, connect banks, or create memory records. Any Google account may register once the installation's Google OAuth application permits it. Google's testing/publishing settings may limit who can complete consent independently of LifeGather's open-registration policy.

## Local setup

Create a Google Cloud OAuth **Web application** client for this installation using [Google's instructions](https://developers.google.com/identity/openid-connect/openid-connect). Configure branding/audience and the exact authorized redirect URI. For the default local setup:

```text
http://127.0.0.1:8787/auth/google/callback
```

Use the same hostname in the browser and configuration; `localhost` and `127.0.0.1` are different origins. Non-loopback deployments require HTTPS. Remote access remains deferred; do not expose the existing public preview while deploying this change.

Create `backend/.env` locally (ignored by Git), using `backend/.env.example` as a template. Add the real client ID and secret there, not in chat, shell history, source, or logs:

```dotenv
LIFEGATHER_PUBLIC_URL=http://127.0.0.1:8787
LIFEGATHER_GOOGLE_CLIENT_ID=YOUR_WEB_CLIENT_ID
LIFEGATHER_GOOGLE_CLIENT_SECRET=YOUR_WEB_CLIENT_SECRET
```

Build the frontend with `npm run build` in `frontend`. In `backend/.env`, set `LIFEGATHER_STATIC_DIR=../frontend/dist`. Then run from `backend`:

```powershell
uv sync --locked
uv run --locked uvicorn lifegather.main:create_app --factory --host 127.0.0.1 --port 8787 --no-access-log
```

If Docker already occupies 8787, leave that running and choose another free local port; change both the public URL and Google's exact callback registration to match. Do not restart or rebuild Docker merely to try the source version.

For Vite development, proxying for `/auth` and `/api` is included. Set the public URL and Google's callback to the actual Vite origin (typically `http://127.0.0.1:5173`) and its `/auth/google/callback` path, then restart the backend. Do not configure a production redirect from an untrusted Host header.

With credentials absent, the login page reports that setup is needed, and login start returns 503. Partial credentials or an insecure non-loopback public URL fail configuration validation. Public URL changes require a backend restart and exact OAuth callback updates.

## Sessions and migration

- Startup upgrades the private `/data/auth.sqlite3` (or local data directory) through packaged Alembic revision `0001_accounts`. Run one application worker for this slice; do not race migrations from independent instances.
- Accounts use Google's normalized issuer plus stable subject. Email/display name can change and are not unique identity keys. No shared workspace or invitation/allowlist logic is introduced.
- Session cookies contain 256-bit random opaque secrets; only SHA-256 hashes are stored. Cookies are host-only, HttpOnly, SameSite=Lax, and Secure on HTTPS. Plain HTTP cookie mode is limited to explicitly configured loopback development.
- Sessions have an absolute seven-day expiry, persist across restarts, and are revoked server-side by logout. Successful new login rotates the browser's existing session. Other devices retain their own sessions until logout/expiry; global session-management UI is not yet implemented.
- Login state is browser-bound, expires after ten minutes, and is atomically single-use. State/browser secrets are hashed in storage; nonce and PKCE verifier are short-lived server-only flow data. Google tokens are verified then discarded, not saved to the browser or database.
- Logout is POST-only and requires matching configured Origin and a session-bound CSRF token. Session/account responses are not cached. Protected `/api/me` derives identity from the session, ignoring client-supplied account IDs.
- Ten login starts per minute per actual connection IP, with at most 1,024 tracked IPs, limits basic single-process abuse. Proxy-wide and distributed abuse control is future deployment work; no forwarded headers are trusted. At most 100 expired rows per table are cleaned per new flow/login; expiry is enforced even before cleanup.
- Database file permissions are restricted on supported systems. SQLite contains personal account details and sessions; protect its parent volume and backups. For an auth-database backup, stop the app and copy the complete private data directory, including any SQLite journal files, then restore only while stopped. General application backup/export UX remains later work.

The image disables Uvicorn access logs to avoid logging OAuth callback query strings. Local source commands above do the same. Reverse proxies must also redact callback query strings; never enable verbose HTTP/token logs with real credentials.

## Verification and limits

Automated tests use synthetic RSA-signed ID tokens and mocked Google metadata/token/JWKS HTTP, exercising the actual Authlib verifier. They cover signature, issuer, audience, expiration, nonce, state/browser binding, replay, failed provider responses, separate subjects with matching emails, session expiry/persistence, and CSRF-protected revocation. UI tests cover loading/setup/login/error/retry, authenticated account, logout, and expiry refresh.

Real Google sign-in still requires owner-configured credentials and an interactive round trip; do not claim it was verified from mocked tests. The next source slice adds [private settings and credential storage](PRIVATE_SETTINGS.md); future domain-data authorization is still required and no personal-memory API is exposed. Google Cloud configuration is installation-wide while each registered identity/session is separate. Light/dark switching remains planned rather than silently expanding this feature.
