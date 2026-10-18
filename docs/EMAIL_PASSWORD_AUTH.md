# Next authentication milestone: email/password and recovery

Requested by the user on 2026-10-17. Implemented in source with a fake email sender in tests; real SMTP delivery has not been configured or exercised. Keep Google sign-in and add ordinary email/password registration and sign-in, verified email ownership, and a Forgot password flow. This extends the existing Google login and reconciliation foundation; provider chat remains later work.

## Intended experience

The sign-in page offers Google, Email and password, Create account, and Forgot password. Registration asks for name/email and sends a verification link before opening a private workspace. The recipient chooses their password only after following that link, so an earlier signup request cannot install an attacker-selected password. Password reset sends a short-lived, single-use link to the verified email address, lets the user choose a new password, then asks them to sign in again. Verification and reset use links, rather than short numerical codes. Signup/setup links expire after 24 hours; reset links after 30 minutes. All are single-use.

After reset, revoke existing LifeGather sessions and outstanding recovery tokens, and send a password-change notification without including the password. User-facing request responses must not reveal whether an email is registered. Failed or delayed mail delivery has a bounded retry/resend path and never reveals tokens in the browser, application logs, or errors.

## Identity and privacy boundaries

Keep one stable private user/workspace ID independent of sign-in method. Migration `0005_email_auth` backfills external Google identities and adds local credential/challenge/throttle tables, preserving user IDs, sessions, memories, settings and vault ownership. Legacy issuer/subject columns remain compatibility metadata; Google authentication now reads the external identity mapping. Password hashes and email keys are separate from provider credentials in the encrypted vault.

Do not silently join accounts based on equal email text. Adding a password to a Google-created account requires an authenticated linking flow and proof of the email address. Google-only accounts cannot gain a local password through an unauthenticated reset request. Duplicates/collisions get a neutral recovery response and private guidance; no automatic data merging. Mailbox-control verification alone is not permission to merge two existing private workspaces.

## Security and implementation requirements

- Store passwords with a maintained Argon2id implementation and per-password salt; never plaintext or reversible encryption. Verify installed package APIs and current parameter guidance when implementing.
- Support long passwords, password managers, paste and Unicode; avoid arbitrary composition rules. The current policy is 15–128 characters and at most 512 UTF-8 bytes, with a small common-password denylist. A comprehensive breach corpus is not implemented and passwords are never sent to an external checking service.
- Use cryptographically random high-entropy verification/reset tokens; store only token digests with user, purpose, expiry and consumed state. Reset and signup tokens cannot be interchanged. Consume atomically; concurrent/replayed/expired requests must fail safely.
- Rate-limit sign-in, signup, verification, reset and resend by account and client source, with bounded persistent state and expiry. Keep responses neutral and avoid easy permanent account-lockout denial of service.
- Reuse opaque server-side sessions, origin/CSRF protections and secure cookies. Native login must rotate the session and never allow a caller to select the owner. Keep secrets out of URLs except the dedicated one-time email token; prevent access logging/referrer leakage and clear the token from navigation after consumption.
- Separate delivery from business logic behind a mockable mail interface. Configure sender, SMTP host/port, authenticated TLS and credentials once per installation in ignored configuration. These are operational server credentials, not a user's email connector or Google sign-in keys. Do not send real mail during development tests.
- New signup/reset must remain safely unavailable until delivery is configured. Existing Google login must keep working independently. No verification bypass for production and no reset-code echo to browser/console.

## Delivery setup still needed

An outbound authenticated SMTP server and an authorized sender address are required for real verification/reset emails. No provider, paid account, domain purchase, mail-server installation or external email delivery has been selected/authorized. Implementation can use a fake sender in tests, but cannot claim end-to-end recovery works until the installation can deliver mail. Choose the delivery setup with the user before enabling it.

## Verification scope

Test native signup/verification/sign-in, bad passwords, normalization/collision policy, expired/reused tokens, concurrent token consumption, resend/attempt limits, generic account-existence responses, delivery failures, logout/session revocation after reset, two-user ownership, Google-only reset rejection, explicit identity linking, and preservation of existing accounts/data through migration. Add UI tests for registration, verification, Forgot password, errors and sign-in states. Test mail through a fake sender; actual delivery is a separate configured smoke test.

Service and UI implementation is present; real delivery remains unverified. Tests cover the native flow and Google compatibility using a fake sender, including concurrent consumption and migration from earlier schemas. See the [implementation plan](superpowers/plans/2026-10-17-email-password-auth.md).

## Installation-owner setup

For a private testing account without Google or SMTP, use the [local account setup command](LOCAL_ACCOUNT_SETUP.md). This explicitly trusts the server owner's email choice and never replaces or links an existing account. Public registration and recovery retain the verification requirements below.

Users only supply their email/password and click verification links. The server owner configures one sender for verification, password recovery and password-change notices. This is separate from Google OAuth and from personal mailbox connectors.

Copy the SMTP settings in `backend/.env.example` to ignored `backend/.env` for source execution, or the root `.env.example` settings to ignored root `.env` for Compose:

```dotenv
LIFEGATHER_SMTP_HOST=smtp.your-provider.example
LIFEGATHER_SMTP_PORT=587
LIFEGATHER_SMTP_USERNAME=your-provider-username
LIFEGATHER_SMTP_PASSWORD=your-provider-password-or-app-token
LIFEGATHER_SMTP_SENDER=sender@your-domain.example
LIFEGATHER_SMTP_IMPLICIT_TLS=false
```

These are placeholders. Port 587 with `false` requires STARTTLS; use the provider's implicit TLS port (commonly 465) with `true` if required. Certificate and hostname verification are enabled; there is no plaintext or skip-verification mode. The provider must authorize the sender. Set the host, username, password and sender together; partial configuration fails startup. Choose an existing provider with the user before configuring it; no domain or paid service is created here. Keep secrets out of source control/chat. Both Compose files forward these optional settings.

`LIFEGATHER_PUBLIC_URL` must be the exact origin users open. Links use this configured origin, never the inbound Host header. The default is `http://127.0.0.1:8787`; use HTTPS for non-loopback deployments. Link tokens are URL fragments, removed by the UI before the explicit completion POST. They are never automatically consumed by page loads, so email link scanners cannot complete password changes.

Existing password and Google sign-in work without SMTP. Signup, reset and adding a password require configured delivery; the UI explains unavailable delivery. Sending is best effort after the neutral HTTP response, not a durable mail queue. Resubmit after checking spam if no message arrives, within resend limits. Delivery errors produce a generic installation log event without recipient, token, credentials or provider error text; failed initial sends remove the unusable challenge. Notifications after successful password changes are best effort and do not roll back the password change.

Existing Google users open Settings → Email and password → Set up password. Open the link in the same signed-in browser. Completing it revokes existing sessions and returns to sign-in. If opened elsewhere, sign in to the intended account and request a fresh setup link. A Google-only account must use this setup flow; Forgot password cannot enable password access for it. A new Google identity that collides with an existing local login is not automatically attached; sign in with the existing method. Adding Google to a native-created account and changing the verified login email are not implemented.

## Limits and operational consequences

- Login: 10 attempts per email and 50 per client connection IP per 15-minute window; expired windows allow retry. Successful logins also count. No permanent lockout.
- Email requests: 3 per email and 20 per client IP per hour, shared across signup/setup/reset. Suppressed requests keep the same neutral reply. Token completion: 30 per client IP per 15 minutes.
- Buckets use hashed keys, expire, and cap at 10,000 rows. Expired buckets/challenges are removed in bounded batches; pending challenges cap at 10,000. Password hashing uses Argon2id defaults (64 MiB, three iterations, four lanes) with at most two concurrent operations per process. Busy requests fail safely and may be retried.
- HTTP auth bodies cap at 16 KiB. Passwords and tokens are redacted from validation errors. Mutations require the exact Origin and JSON; signed-in setup/completion also require the session CSRF token. Connection IP is used without trusting forwarded headers; a reverse proxy may therefore share a limit across its users until a trusted-proxy design is explicitly configured.
- Local login rotates the session, and reset/setup revoke every session for that account and invalidate outstanding challenges. Tokens are stored as SHA-256 digests and password credentials as salted Argon2id hashes. Domain exports exclude these authentication tables; operator database backups include them and must remain private.
- Migration 0005 does not rewrite private domain records. Prefer a tested database snapshot plus matching source for rollback; downgrading drops the new credential/challenge/identity tables and disables native login while retaining workspace rows. Do not downgrade a live database casually.
- The running/published Docker image does not gain this source feature until a separately approved rebuild. No image build, upload, restart, SMTP configuration or real mail send was performed by this implementation task.

References checked 2026-10-17: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
