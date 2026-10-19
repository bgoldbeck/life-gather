# Persistent contextual assistant

Baseline 9295672 / v0.46.0 / migration 0022. Manual entry is merged in PR 67;
the separate private-record-export branch still contains only its plan.

User-approved outcomes: remove Chat from sidebar navigation; one always-mounted
assistant across pages, docked at the bottom by default, with edge controls
and collapse/expand but no close button. Keep history, drafts and pending work
through navigation/collapse. Store only layout preferences per account/browser.

Capture the active page and explicit record when submitting each message. Resolve
the record on the server, display its actual name in the dock, and retain a
versioned context snapshot for safe retries and stale-edit detection. Do not let
later page changes redirect writes or cause old history to navigate the browser.

Add a bounded local Organize action (default in the dock) for explicit open/edit
requests and sourced profile changes. A unique 'edit my F150' request opens Assets
to the actual owned record; duplicate names require choosing a record. A request
to add a VIN asks for the value if missing; supported supplied profile details
use ProfileService validation, correction history and provenance. No invented
values, inferred identity merge, unrestricted model writes or provider call is
needed for these explicit commands. Ordinary Ask AI remains available and gains
the explicitly selected read context only under existing external-data consent.

Make domain changes and the saved Chat result atomic with the pending/cancelled
turn check. Pin record/version/text in retry fingerprints while preserving old
request identities when context is absent. External MCP clients receive explicit
context read/action tools under their own authenticated request; no global
browser focus, cross-client ambient context or remote browser-control bridge.

Test user isolation, ambiguous names, context changes, stale/conflicting edits,
cancel/retry atomicity and history replay; keep read-only model permissions.
Test dock persistence, collapse without remount, navigation, account-scoped layout,
context labels, pending navigation guards and responsive light/dark layouts.
Run full checks, visual inspection, graph refresh, commit/push/PR/merge/cleanup.
Keep the deliberately bundled v0.46.0 version, then publish one verified image
containing manual entry and contextual chat. No app/TrueNAS redeployment is implied.

Verified implementation: persistent bottom/top/side dock, collapse without remount,
per-account layout, exact selected-record reads, explicit asset navigation, sourced
profile writes and atomic turn completion. Default Assistant is local-only; Ask AI
remains a separate explicitly chosen read-only mode. No resize/drag system or live
external browser bridge is included. Narrow screens use bottom docking.

Validation: full backend suite 461 passed, followed by five context tests including
the additional rollback/concurrent-retry test; focused chat/MCP/scan regression
suite 35 passed. Frontend 206 tests passed; strict mypy, Ruff, TypeScript, lint,
format and production build passed. Compose configurations validate; migration
head remains 0022_change_origins. Synthetic browser checks covered manual truck
entry, page context, VIN save, navigation from Settings, side docking, collapse,
390px mobile and light/dark appearance. The existing Docker installation was not
changed. Graphify refreshed to 2909 nodes / 11591 edges; its known AssetsPanel
parser limitation remains, with TypeScript and UI tests authoritative.
