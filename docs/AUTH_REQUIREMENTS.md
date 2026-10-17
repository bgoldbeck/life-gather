# Next milestone: Google sign-in and individual data

User decision, 2026-10-16: complete the Phase 0 Docker preview first, then add Google sign-in and per-user data isolation before accepting personal memory data.

This supersedes the original single-user assumption. A self-hosted installation may have multiple users, each with their own private records. This does not introduce public SaaS infrastructure.

## Required behavior

- User decision, 2026-10-17: allow registration by any Google account without invitations or an allowlist. Create an empty private workspace on first login. No shared spaces or cross-user data access.
- Every user supplies their own AI provider credentials, email and bank connections. Isolate chats, files, graph records, connector state, schedules, research, usage tracking, and settings. Installation OAuth client secrets remain server configuration, not another user's provider connection.
- Offer a straightforward **Continue with Google** sign-in using OpenID Connect.
- Use Google's stable issuer and subject identifiers to identify an account; do not use a mutable email address as the ownership key.
- Keep Google client secrets and login validation on the server. Validate the authorization response, including state, nonce, signature, issuer, audience and expiration, using a supported library.
- Establish a server-managed session with an HttpOnly cookie, appropriate SameSite protection and Secure cookies for HTTPS deployments. Provide logout and session expiration. Do not place tokens in browser local storage.
- Enforce ownership in framework-independent services and bounded database queries. Browser input must never decide the acting user. Every memory, source, document, relationship, search result, correction, export and derived record must be scoped to an authenticated owner.
- Apply the same ownership checks to HTTP and MCP adapters. Authentication must not be implemented as a frontend-only gate.
- Do not expose other users' records through IDs, relationship traversal, text search, filenames or shared caches.
- Use Alembic migrations for user/session tables and all ownership schema changes.
- No personal memory endpoints should become available before these controls exist.

## Acceptance evidence

- A new Google account can register, sign in, and sign out using supported callback URLs, without an invitation or email allowlist.
- Missing, invalid, expired and replayed login responses fail safely.
- Unauthenticated requests cannot access personal data.
- Two fixture users cannot read, search, modify, link, export or delete each other's records, including by guessing identifiers.
- Tests use mock identity-provider responses, with no production Google credentials or personal data.
- Sessions remain valid only according to the documented persistence, expiry and revocation policy.

## Resolve at implementation time

- Configure the Google Cloud OAuth client, consent screen, client ID/secret, exact redirect URLs and HTTPS origin for deployment.
- Open registration is explicitly selected. Define abuse controls and rate limits without introducing an invitation or email allowlist requirement.
- Choose the supported authentication library and define session persistence, expiration and CSRF controls.
- Update the original project plan and repository instructions to reflect per-user ownership when implementing this milestone. Those existing local planning files have been preserved during Phase 0.

Reference: [Google OpenID Connect documentation](https://developers.google.com/identity/openid-connect/openid-connect).
