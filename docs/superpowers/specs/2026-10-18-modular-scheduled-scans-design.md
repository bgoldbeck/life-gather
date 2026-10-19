# Modular scheduled email scans

User intent: private email scans started on request or a user-defined schedule,
never triggered by email arrival. User chose email first, with mailbox connection
as a prerequisite, and explicitly requested modular scan implementations. Existing
Google sign-in is not mailbox permission. No live credentials, personal ingestion,
paid services, image publication or deployment are part of development verification.

## Architecture and release boundaries

1. Gmail connection: separate explicit read-only Google OAuth consent, fixed
endpoints, PKCE, one-time session-bound state and existing encrypted credential
vault. Add private mailbox settings and disconnect. Reuse installation client
configuration with an additional callback; do not change login scopes. No mail
sending/deletion, arbitrary URLs or model access to secrets.
2. Manual email scans: durable owner-scoped generic runs and typed handler registry.
The first handler imports bounded Gmail message text as original evidence without
an AI call or an inventory write. Fixed requested time range, optional query,
progress/cancel, stable mailbox/message identity and per-run checkpoints prevent
duplicate evidence across retries/reconnections. Explicit truncation and omitted
attachments. Sources remain private and inspectable. No generic plugin execution.
3. Schedules: per-user daily/weekly wall time and IANA timezone, next-run display,
pause/edit, bounded catch-up and durable due-run identity. SQLite claims/leases,
no overlapping runs per connection, checkpoint recovery and cancellation. Schedules
only enqueue registered handlers; Gmail and future scan targets share ownership,
permission, progress and lifecycle contracts. No Redis or external scheduler.

## Contracts

Domain services are independent of HTTP/MCP. Adapters derive the actor from the
session; background runs derive it from their durable owned record and recheck
account/connection/permissions at safe boundaries. Saved configuration is data;
source content cannot choose a handler, tool, account, endpoint or broader scope.
Registry metadata describes source kind and required permissions; each handler
validates configuration and supplies a stable overlap key. The runner owns state,
leases, cancellation and progress; the scheduler owns recurrence and enqueue only.

Gmail refresh credentials never leave the encrypted vault. Gmail account identity
comes from users.getProfile after verified token scope, independent of the account
used to sign into LifeGather. Stable per-owner mailbox identity survives reconnect.
Disconnect removes local secrets and blocks queued/future work; users may separately
revoke Google permissions. Do not revoke unrelated login grants automatically.

## Recurrence and recovery

Persist UTC instants and explicit wall time/timezone. Validate timezone names.
For missing DST wall times advance to the first valid time; for repeated times
run once at the first occurrence. Compute future occurrences from local calendar
rules, not 24-hour durations. Recover at most one missed occurrence per schedule,
then advance beyond now instead of flooding the mailbox after downtime. Pause
prevents further work; cancellation is cooperative at bounded network/transaction
boundaries and preserves completed evidence. Retrying never duplicates sources.

## Acceptance

Synthetic fixed-endpoint OAuth/provider tests, strict owner/CSRF/state checks,
credentials absent from responses/storage plaintext, scope denial and disconnect;
manual scope enforcement, bounded payloads, HTML treated as data, idempotent imports,
cancel/restart recovery, concurrency/lease safety, timezone/DST/overlap/missed-run
behavior, migration preservation, snapshot recovery, private MCP and accessible UI.
Live Gmail access and installation OAuth verification remain explicitly unverified.

## Sources checked

- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get

User standing instruction: implement routine decisions in this root chat without
subagents or repeated approval stops; commit/push/PR/merge/cleanup each completed
feature. Spec and release-specific tests are refined before implementation.
