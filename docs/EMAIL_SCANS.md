# Private email connections and scans

## Gmail connection (v0.34.0)

Settings → Email connections → Connect Gmail opens a separate Google read-only
mailbox consent flow. It does not change LifeGather sign-in scopes and can connect
a different Gmail/Workspace mailbox. Connecting alone imports nothing, sends no
mail to AI, and does not grant send/modify/delete capability to this integration.

The installation owner must configure the existing Google OAuth client and the
32-byte vault key outside data/static storage. In the same Google Cloud project:

1. Enable the Gmail API.
2. Add `PUBLIC_URL/auth/gmail/callback` as another authorized redirect URI on the
   Web application OAuth client; retain `/auth/google/callback` for normal login.
   Local example: `http://127.0.0.1:8787/auth/gmail/callback`.
3. Configure the consent screen for
   `https://www.googleapis.com/auth/gmail.readonly`. Add permitted test accounts
   when using Google's Testing mode. Do not put a client secret in the image.
4. Restart/reconfigure the installation as needed, then let each user connect
   their own mailbox from Settings. This development task does not configure a
   real Google project or connect personal mail.

Google classifies Gmail read-only as a restricted scope; distribution, verification,
security assessment and test-mode refresh-token lifetimes depend on the project's
status and applicable Google policies. Do not assume ordinary sign-in verification
covers mailbox access. Check the official requirements for the installation before
public distribution; no paid service or verification purchase is enabled here.

The refresh token is stored only in the existing authenticated encryption vault.
Access tokens are transient. OAuth state is hashed, one-time, ten-minute and bound
to the signed-in account, current session and browser cookie; PKCE protects the
code exchange. Fixed Google endpoints, bounded responses and no redirects prevent
untrusted source content from choosing a credential destination.

Disconnect removes this app's local encrypted credential. Imported evidence and
earlier database backups remain. It does not revoke other Google sign-in grants;
users can separately review permissions at https://myaccount.google.com/connections.
Reconnect preserves the private mailbox identity and advances its revision, so a
stale disconnect cannot remove the new connection. Removing its credential through
the existing vault also disables the mailbox.

## Modular scan rollout

The scheduled-scans implementation plan separates source handlers from durable run
lifecycle and recurrence. Gmail connection is the prerequisite; manual scanning,
run progress/cancellation/recovery and daily/weekly schedules follow as tested
releases. Do not interpret a connected mailbox as an enabled scan or a completed
scheduler. No email-arrival ingestion trigger is planned.

- Design: `superpowers/specs/2026-10-18-modular-scheduled-scans-design.md`
- Plan: `superpowers/plans/2026-10-18-modular-scheduled-scans.md`

## Official references

- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2#expiration
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.getProfile

Verification uses synthetic accounts and mocked HTTP only. Live Gmail access,
consent-screen configuration and refresh-token longevity remain unverified.
