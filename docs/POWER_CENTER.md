# Power Center

Delivered in v0.58.0. Open **Power Center** in primary navigation to inspect what
this private workspace can do, what needs setup and observed processing health.
Settings also shows connection capability changes. This is not a completeness or
productivity percentage.

## Capability readiness

Scoring catalog **1** has a fixed 100-point denominator:

| Outcome | Weight |
| --- | ---: |
| Local capture and evidence recall | 20 |
| Inventory and sourced corrections | 15 |
| Stated maintenance tasks | 10 |
| Private records/original downloads | 10 |
| Sourced AI answers | 15 |
| Requested photo/receipt reading | 10 |
| Requested Gmail text evidence | 10 |
| Requested Gmail purchase discovery | 10 |

Ready outcomes earn their weight. Unknown/stale dependencies contribute only to
the possible upper bound; blocked, disabled and failed dependencies earn zero.
Different bounds mean **Incomplete**, never an invented precise score. Planned
integrations are excluded. Redundant providers cannot increase an outcome's weight.
One recent working Gmail alternative preserves text-scan availability; other
mailboxes still show their own problems. Source count groups AI by provider and
Gmail by mailbox and excludes the local workspace.

Local readiness means supported services are installed and the snapshot can read
the database; it is not a full file-integrity/recovery test. AI checks storage
configuration, explicit external-AI permission, a supported connection, a saved
Chat model/default and the existing daily limit. A default is not a reachability
test; individual Chat requests can select another connection/model. Discovery
selects its model at run creation and does not require a saved Chat default.
Photo reading still requires an actually vision-capable model.

## Health and freshness

Checks read one owner-scoped PostgreSQL snapshot. Metadata uses the existing
100-credential, 10-mailbox and 5-schedule limits; recent failed/expired diagnostics
show at most ten runs with an explicit incomplete-overview warning. Seven-day
activity counts completed scans and newly imported messages, not discovered assets;
partial/failed runs are excluded from these totals.

Gmail processing observations are recent for **24 hours**; data is labelled current
for **seven days** after its last successful scoped scan. This never means the
whole mailbox was scanned. Grant revisions must match, so reconnecting invalidates
old observations. Latest completed/failed outcomes determine processing status;
cancelled/queued runs cannot erase failure. An expired running lease indicates
expected work needs recovery; idle manual uploads do not. Recent failed runs remain
inspectable as history even after recovery.

Paused schedules are counted separately. Enabled schedules whose dispatch is
blocked or over five minutes overdue get an inspect action. Failed-run links use
exact private IDs; other remedies reuse Settings, Chat and Scans. Nothing restarts
a worker or starts a scan when Power Center opens.

While Power Center or its Settings summary is mounted, local checks refresh every
minute when visible. Snapshots expire after five minutes; requests time out after
15 seconds. Manual Check all/per-source checks refresh the same bounded snapshot.
Failures preserve original observations and checked times; expired snapshots show
stale labels. There is no background external probe.

Each saved credential remembers only the provider's last answer to it
(v0.85.0, migration `0036_credential_auth_state`). A requested AI request that
succeeds marks that key working; an AI connection shows **Ready** while a request
succeeded within 24 hours, and stays unverified otherwise. A `401`/`403` from
OpenAI, Claude or Gemini, a Gmail token refresh answered `invalid_grant`, or a
Gmail `401` marks the connection as needing a reconnect. Power Center then shows
it as needing attention with **Reconnect**: Gmail opens Google read-only consent in
one click; an AI key opens its Replace form in Settings (paste a new key). Saving
a new key or completing Gmail consent clears the prompt. Google revocation is
still only noticed when requested processing runs; there is no probe.

Raw provider errors, secrets, credential IDs, nonces and ciphertext never appear
in diagnostics. Credentials are not decrypted; no provider endpoint is called.
Paid/remote probes, richer live-model diagnostics and scanner integrations require
later scope.

## Connection changes and privacy

Source cards preview supported outcomes and dependencies before connection.
Settings reports **Newly available to request**, **Already available**, **Still
needs setup** and lost capabilities. Unknown health is distinct from configured
availability, which never claims completed discoveries.

The comparison baseline saves only supported capability IDs in account-keyed
`sessionStorage` in this browser tab, surviving Gmail consent. No records, addresses,
credentials or health logs are stored there. Storage is optional; current prerequisite
explanations work without it. Account switches remount the workspace; aborted late
reads cannot populate another account's snapshot.

HTTP `GET /api/power` and read-only MCP `power_center_get` (empty `data`) share
`PowerCenter`. Existing session, MCP origin/CSRF, response-size and no-store guards
apply; neither adapter accepts an acting user ID. No health table, migration,
dependency, ingestion scheduler, export-format or recovery change.

## Verification

The source release passed 643 backend tests (`uv run pytest` from `backend/`),
Ruff check/format, strict mypy and `uv build`. Frontend verification from
`frontend/` passed 304 tests, lint, typecheck, formatting and production build.
The existing Vite large-bundle advisory remains; no new dependency was added.
All four offline PowerShell release/launcher verification scripts passed.

Synthetic browser QA covered primary navigation, honest empty readiness, filters,
local refresh, Settings remedies, saved dark mode, 390px layout, keyboard refresh
and unsent assistant drafts across navigation docking. A local Windows MIME
registry override was needed for the QA server's JavaScript; the Linux release
uses its normal MIME configuration. No live mailbox/provider call was made.
Code-only single-worker Graphify and HTML were refreshed; the graph contains
3,614 nodes and 14,823 edges (one test file yields no symbols). Image smoke and
publication follow the tested source merge; the running installation is separate.
