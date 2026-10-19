# Private email connections and scans

## Daily/weekly schedules (v0.36.0)

Scans → Scheduled scans creates a schedule for a connected Gmail mailbox. Choose
a timezone such as `America/Los_Angeles`, daily/weekly frequency and local time,
the preceding 1–30 days, search and message cap. The app must be running; your
browser can be closed and you can be signed out. Work is queued when the worker
checks due schedules; a busy single worker can delay dispatch. There is no
email-arrival trigger, paid external scheduler or additional service.

Five schedules per user are supported; edit an existing schedule to reuse a slot.
Manual and scheduled runs share the 20-runs/day/user cap and one active run per
mailbox. Overlapping occurrences are skipped and shown in schedule status. A
disconnected or changed local mailbox grant, unavailable handler or invalid scope
blocks and pauses dispatch. Reconnect in Settings and explicitly Resume; this
adopts the current connection. A remote provider failure is shown on the run;
check that run and reconnect if needed. No credentials appear in the schedule API.

After downtime only the latest missed occurrence is queued; older missed windows
are not replayed. Each run reads a frozen window ending at its scheduled UTC
instant. Overlapping lookbacks safely deduplicate email evidence. Message caps can
leave mail unprocessed, so narrow the query or dates if a run reports truncation.
This scheduler is not a guarantee that every mailbox message will be imported.

Schedules preserve local calendar time through timezone changes: a missing spring
time advances to the first valid local minute; a repeated autumn time runs once
at its first occurrence. Pause prevents new dispatch and retains history; cancel
an already queued/running job separately. Editing or resuming resets the next run
to a future occurrence, with optimistic revisions to protect concurrent edits.
Restore the database/vault as usual; schedules and jobs are durable SQLite data.

Source handlers materialize date windows through a typed contract. Recurrence,
dispatch, leases, cancellation and checkpoints remain independent of Gmail. Only
server-registered handlers are accepted; there is no arbitrary uploaded code.
Private MCP `scan_schedule_list` reads status without starting work. App chat
remains read-only; conversational scan-start tools are not enabled in this slice.

Timezone implementation follows Python's first-party
[zoneinfo documentation](https://docs.python.org/3.13/library/zoneinfo.html), using
the `tzdata` package when system IANA data is unavailable.

## Requested scans (v0.35.0)

Open Scans after connecting Gmail in Settings. Choose dates (UTC), an optional
Gmail search and a message cap, then Start email scan. Scans do not run when mail
arrives. No AI requests or assets are created during import. Use Memories → Email
evidence to inspect/correct the saved text with original history preserved.

Each run covers at most 31 days and 50 messages, with 20 runs per user per day.
Only supported inline plain/HTML text is imported; attachments and remote resources
are not fetched. Large responses stop the run safely. Text is capped at 4,000
characters and marked when truncated or parts are omitted. Original Gmail message
identity and headers accompany the excerpt. This is not a full mailbox backup.

The server processes one item at a time with a durable checkpoint. Restart resumes
the last committed checkpoint; at most three claims and ten minutes per claim.
Cancel stops at the next safe boundary; already saved evidence remains. Identical
message identities in the same user's mailbox are saved once, including reconnects.
Changed content under the same identity fails safely rather than overwriting history.

Typed handlers register source-specific scope, permission checks and bounded steps.
The generic run service owns leases, progress, cancellation, evidence transactions
and recovery. A handler rechecks authorization in the evidence transaction. Adding
a source needs a handler, tests and its UI, not another queue or scheduler. No
arbitrary plugin code can be uploaded through the app. Private MCP `scan_list` and
`scan_get` expose read-only status and paginated evidence references.

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
