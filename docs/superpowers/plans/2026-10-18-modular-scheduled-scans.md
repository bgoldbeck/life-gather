# Modular scheduled email scans implementation

Spec: ../specs/2026-10-18-modular-scheduled-scans-design.md
Baseline: main 52a2fcf, application v0.33.1. Root-only execution.

1. Gmail OAuth connection (v0.34.0): migration 0017 adds owner-bound mailboxes
and one-time OAuth flows; use existing vault, fixed Google endpoints and separate
callback; add settings UI and private list/disconnect. Test protocol/security,
owner separation, scope rejection, stale disconnect/reconnect and migration.
Relevant checks from backend/ and frontend/, strict typing, graph refresh, release.
2. Manual modular email scans: generic durable run service and typed registry,
bounded Gmail handler and private evidence import; request/run history/cancel UI,
source inspection and private MCP. Synthetic wire, replay, recovery, isolation,
limits and permission tests before release. Refine interfaces after step 1.
3. Daily/weekly schedules: durable recurrence/dispatch using the same handlers,
timezone/DST, next-run/pause/edit, catch-up/overlap/restart tests and schedule UI.
Refine interfaces after step 2; no separate Gmail timer or fake scan placeholders.

Preflight: steps share owned mailbox identity and encrypted credential references;
mailbox reconnect must preserve identity while changing revision so old work stops.
Runs use immutable configuration snapshots; schedules enqueue handlers, not HTTP
calls. Revocation and cancellation are checked again at write boundaries.
Do not add AI extraction, bank integration or remote capture to this scope.


Step 1 implementation: fixed Gmail OAuth consent/profile/refresh endpoints; no
mail reads yet. Owned mailbox identity and revision, existing encrypted vault,
PKCE/hashed single-use session/browser state, Settings connect/disconnect and
separate callback. Migration 0017 includes composite owner credential protection.
Observed missing-module/UI tests before implementation; synthetic consent/scope,
flow/replay/privacy, vault revocation and snapshot tests now pass. No subagents.


Step 1 verified: 333 backend / 129 frontend tests pass; Ruff lint/format,
strict mypy (153 files), TypeScript, Oxlint, Prettier and wheel/frontend builds
pass. Graphify refreshed 2177 nodes / 8493 edges and HTML. Synthetic HTTP tests
cover fixed endpoints, scope refusal, redacted failures, CSRF, one-time callback,
owner separation, disconnect/reconnect, expired/pending flows, vault removal and
snapshot recovery. Self-review: explicit consent only, no mail/AI read on connect,
no secret in API results; installation setup and live verification limits recorded.
No real account connection, provider call, image build/upload or deployment.

Step 2 implementation: fixed typed registry, durable per-user SQLite run/item
tables, one-item atomic checkpoints, leases, idempotent request replay, overlap
guard, cancellation and bounded crash recovery. Gmail handler verifies the
connected account, rechecks permissions before requests and inside writes, bounds
dates/messages/response bytes/MIME depth, omits attachments and imports only text.
Scans UI requests/retries, progress/results and source inspection; email evidence
joins existing Memories correction history. MCP scan_list/scan_get are read-only;
chat remains read-only and does not silently gain scan-start permissions.

Step 2 verified: full baseline plus new runner tests: 339 backend tests pass;
six additional boundary tests pass (345 total). 130 frontend tests, Ruff lint and
format, strict mypy (166 files), TypeScript/Oxlint/Prettier, frontend and wheel
builds pass. Graph refreshed 2329 nodes / 9052 edges. Synthetic tests cover two-user
HTTP/MCP/CSRF, snapshot/checkpoint recovery, stale leases, cancellation, three-claim
cap, replay, source deduplication, wrong account, disconnect during message read,
untrusted message identity, oversized response and MIME omission. No live Gmail,
AI, Docker or deployment action. Daily/weekly recurrence remains step 3.
