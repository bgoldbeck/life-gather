# Email/password authentication implementation plan

Continue the requested native signup/recovery milestone alongside Google. Main chat only. Preserve existing user IDs, APIs and unrelated edits. No live email, paid setup, Docker operation or automatic source push.

## Design and limits

Migration 0005 backfills external Google identity records, adds local password credentials, expiring challenges and persistent throttles. Legacy issuer/subject columns remain compatibility metadata; Google authentication uses the new identity mapping. Keep all existing workspace IDs and private foreign keys.

Signup initially asks for name/email; the recipient chooses a password only after receiving a verification link, preventing an attacker from selecting their pending password. Tokens contain 32 random bytes; store SHA-256 digests only, bind purpose/user, consume atomically. Signup and signed-in password setup expire in 24 hours; reset in 30 minutes. Revoke all sessions and pending tokens on password changes. Never reset a Google-only identity into password access. Existing Google users explicitly request password setup while signed in and must confirm the emailed token in that same account session. No automatic account linking by equal email.

Use argon2-cffi Argon2id defaults, verifying installed signatures. Passwords: 15–128 characters, at most 512 UTF-8 bytes; allow Unicode/paste/password managers and reject a small documented common-password set. No comprehensive breach corpus or external password checks in this slice. Email matching case-folds ASCII local parts and domain, with no provider-specific dot/plus rewriting; SMTPUTF8 local parts are unsupported.

SMTP is optional and mockable; require verified implicit TLS or STARTTLS, explicit sender/credentials and timeout. Without delivery, existing native and Google login still work, but signup/link/reset are disabled. Links use the configured origin and URL fragments; clear fragments immediately and consume only on explicit POST, never GET/page load. Tests use a fake sender; actual mail delivery needs separate configuration and smoke testing.

HTTP checks exact Origin, JSON content type and Fetch Metadata; signed-in setup also uses session CSRF. Auth bodies max 16 KiB; redact validation and provider errors, suppress caching/referrers, and never persist plaintext passwords/tokens in browser storage. Neutral signup/reset replies do not reveal account existence or delivery failure.

Persistent attempt limits: login account 10/client 50 per 15 minutes; mail account 3/client 20 per hour; token consumption client 30 per 15 minutes. Hash bucket keys, expire/clean up bounded batches, cap total active buckets at 10,000. Spend attempts before expensive verification/send and do not roll them back on invalid credentials. Use connection IP, not untrusted forwarded headers.

## Work and verification

1. Add failing service tests for signup/login/reset, hashing, token purpose/expiry/replay, Google collisions, explicit linking, concurrency, limits, mail failures and migration preservation.
2. Implement models/migration, identity/session helpers, native auth service and mockable SMTP adapter. Keep Google tests passing.
3. Add thin routes, request caps and HTTP security tests; add accessible signup/login/recovery, explicit token completion, and signed-in password setup UI with interaction tests.
4. Document setup/limitations; verify backend/UI lint, types, tests, build, package/migration and source graph; create a local feature commit. Stop before live delivery or chat work.

## Completion evidence

Verified 2026-10-17: 74 backend tests and 17 UI tests pass, plus nine offline publishing-script scenarios. Backend Ruff lint/format, mypy, wheel build, native module/migration packaging and migration/ORM comparison pass; frontend lint/type/format/build and both Compose configurations pass. Local code-only graph refreshed to 731 nodes and 1961 edges, with HTML export. Native registration/recovery UI and fake-sender flows are implemented; no real SMTP delivery, Docker build/upload/restart, source push or merge was performed. Existing Google login and private workspace IDs are preserved through migration 0005.
