# Google registration and login implementation plan

Execution: main chat only, as required by user policy. The user requested implementation of the first feature; no delegation or Docker rebuild/upload.

Goal: complete a testable Google OIDC login/logout slice with private account identity and persistent server-side sessions. Spec: `docs/AUTH_REQUIREMENTS.md` and `docs/superpowers/specs/2026-10-17-personal-discovery-design.md`.

Architecture: Authlib handles authorization URL generation, code exchange with PKCE, and signed ID-token validation. SQLite/SQLAlchemy services persist short-lived single-use login flows, issuer/subject account identities, and hashed session tokens. Alembic migrations are packaged with the backend. React displays configuration/loading/error/login/account states and uses same-origin session APIs; no browser token storage.

## Tasks

1. Add migration-backed account/session/flow storage in `backend/src/lifegather/auth/` and packaged `migrations/`. Write tests for identity by issuer/subject (never email), single-use/expired flow rejection, session expiry/revocation/restart persistence, and bounded expired-record cleanup. Store only hashes of browser/session bearer secrets.
2. Add `config.py` Google client settings and fixed public origin, default disabled when credentials are absent; permit plain HTTP only on loopback development origins. Add Authlib provider wrapper and thin `/auth/google/start`, `/auth/google/callback`, `/auth/session`, `/auth/logout`, and protected `/api/me` adapters. Test cookies, CSRF/Origin, replay, invalid signatures/claims, provider errors, and cross-account session separation with synthetic signed tokens and mocked provider HTTP.
3. Add a React auth gate and account/logout control; retain the shell behind login. Test anonymous, unconfigured, loading/error/retry, authenticated, logout, and expired-session behavior. Proxy `/auth` and `/api` in Vite.
4. Document exact callback configuration and local testing, session lifetime/revocation, migration startup, data stored, and limits. Live Google verification requires the installation owner's OAuth client credentials configured locally; never request secrets in chat. Preserve existing edits in `docs/AUTH_REQUIREMENTS.md` and `docs/FIRST_TASK.md`.
5. Run backend pytest/Ruff/mypy, frontend tests/lint/type/format/build, migration upgrade/restart checks, and local source graph refresh. Review source and test coverage in the main chat. Commit only intended passing work. No push, hosted CI, personal-data endpoints, or Docker operations.

## Review focus

- Invalid/expired/replayed authorization cannot create accounts or sessions.
- Session cookies are HttpOnly, host-only, SameSite=Lax, and Secure on HTTPS; no tokens appear in JSON or storage.
- Login uses a fixed configured callback, not untrusted Host/forwarding headers.
- Users with matching emails but distinct subjects remain separate; browser-selected identity never controls ownership.
- Provider/network failure leaves a recoverable UI and no partial login; disabled configuration exposes no secret values.

Not included: personal-memory storage/isolation tests against future domain tables, encrypted connector vault, theme switch, live provider account creation, remote exposure, or container publication. Those remain later slices. This feature establishes the authenticated principal future domain services must use.
