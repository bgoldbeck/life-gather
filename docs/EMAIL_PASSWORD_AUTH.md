# Next authentication milestone: email/password and recovery

Requested by the user on 2026-10-17. Planned, not implemented. Keep Google sign-in and add ordinary email/password registration and sign-in, verified email ownership, and a Forgot password flow. This is the next milestone before provider chat; the reconciliation service slice is already committed.

## Intended experience

The sign-in page offers Google, Email and password, Create account, and Forgot password. Registration sends an email verification link before opening a private workspace. Password reset sends a short-lived, single-use link to the verified email address, lets the user choose a new password, then asks them to sign in again. A link is the proposed first mechanism; short numerical codes would require stricter challenge/attempt handling and are not needed to deliver the requested recovery experience.

After reset, revoke existing LifeGather sessions and outstanding recovery tokens, and send a password-change notification without including the password. User-facing request responses must not reveal whether an email is registered. Failed or delayed mail delivery has a bounded retry/resend path and never reveals tokens in the browser, application logs, or errors.

## Identity and privacy boundaries

Keep one stable private user/workspace ID independent of sign-in method. The existing `users` schema stores Google issuer/subject directly; supporting multiple identities requires an explicit migration, preserving user IDs, sessions, memories, settings and vault ownership. Local credentials and external Google identities must be separate records with their own uniqueness constraints.

Do not silently join accounts based on equal email text. Adding a password to a Google-created account requires an authenticated linking flow and proof of the email address. Google-only accounts cannot gain a local password through an unauthenticated reset request. Duplicates/collisions get a neutral recovery response and private guidance; no automatic data merging. Mailbox-control verification alone is not permission to merge two existing private workspaces.

## Security and implementation requirements

- Store passwords with a maintained Argon2id implementation and per-password salt; never plaintext or reversible encryption. Verify installed package APIs and current parameter guidance when implementing.
- Support long passwords, password managers, paste and Unicode; avoid arbitrary composition rules. Select and document the minimum/maximum length and compromised-password policy before implementation.
- Use cryptographically random high-entropy verification/reset tokens; store only token digests with user, purpose, expiry and consumed state. Reset and signup tokens cannot be interchanged. Consume atomically; concurrent/replayed/expired requests must fail safely.
- Rate-limit sign-in, signup, verification, reset and resend by account and client source, with bounded persistent state and expiry. Keep responses neutral and avoid easy permanent account-lockout denial of service.
- Reuse opaque server-side sessions, origin/CSRF protections and secure cookies. Native login must rotate the session and never allow a caller to select the owner. Keep secrets out of URLs except the dedicated one-time email token; prevent access logging/referrer leakage and clear the token from navigation after consumption.
- Separate delivery from business logic behind a mockable mail interface. Configure sender, SMTP host/port, authenticated TLS and credentials once per installation in ignored configuration. These are operational server credentials, not a user's email connector or Google sign-in keys. Do not send real mail during development tests.
- New signup/reset must remain safely unavailable until delivery is configured. Existing Google login must keep working independently. No verification bypass for production and no reset-code echo to browser/console.

## Delivery setup still needed

An outbound SMTP server or transactional-mail provider and an authorized sender address are required for real verification/reset emails. No provider, paid account, domain purchase, mail-server installation or external email delivery has been selected/authorized. Implementation can use a fake sender in tests, but cannot claim end-to-end recovery works until the installation can deliver mail. Choose the delivery setup with the user before enabling it.

## Acceptance before local commit

Test native signup/verification/sign-in, bad passwords, normalization/collision policy, expired/reused tokens, concurrent token consumption, resend/attempt limits, generic account-existence responses, delivery failures, logout/session revocation after reset, two-user ownership, Google-only reset rejection, explicit identity linking, and preservation of existing accounts/data through migration. Add UI tests for registration, verification, Forgot password, errors and sign-in states. Test mail through a fake sender; actual delivery is a separate configured smoke test.

Implementation planning must specify concrete token lifetimes, retention, rate limits, request/body limits, migration and rollback behavior, and email sender requirements. This document records the requested next milestone; it does not mark password authentication or email delivery complete.

References checked 2026-10-17: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
