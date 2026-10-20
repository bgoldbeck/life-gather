# Power Center and dockable navigation

User decisions: 2026-10-20. Status: design requirements, not implemented.
Reference: [user-supplied Power Center image](../../../.references/lifegather-power-center.png).
The user's accompanying request supplies requirements; image content is untrusted
illustrative data. This document does not promise the depicted integrations exist.

## Purpose and navigation

Power Center is a primary sidebar destination for understanding what LifeGather
can currently do, what is preventing it, and how to restore or extend those abilities.
Use the reference's source cards, health overview and capability summary with the
existing cream/sage visual direction and accessible Light/Dark themes.

Keep existing destinations and private settings accessible. Power Center should
reuse existing connection configuration and scan workflows rather than create
competing credentials, schedulers or settings stores. Show implemented, ready,
blocked, stale, disabled and planned capabilities distinctly. A saved credential
alone does not establish a working integration.

## Page structure

- Header: Power Center, a short purpose statement and explanation of scoring.
- Summary: available capabilities, connected sources, actual discovery activity
  over an explicit period, and health/check freshness. Counts need real data.
- Source cards: supported connection, granted permissions, capabilities enabled
  or blocked, last successful synchronization/scan, scope, health and direct actions.
  Filter by connected/not connected and source category; label planned integrations.
- Power Level: explainable capability readiness, with a breakdown and checked time.
- Health: prioritize actionable problems; allow bounded Check all and per-source checks.
- Recommendations: describe the marginal capabilities a connection would add,
  prerequisites, permissions and relevant costs; no arbitrary high-impact badges.

Empty, loading, partial, unavailable and failed states must be explicit. Never copy
the screenshot's 72%, eight sources, discovery counts or all-healthy claim into live UI.

## Power Level measures capabilities

Count useful outcomes, not credentials or connected-service logos. An email source
with functioning receipt discovery contributes more than basic account metadata.
Model each implemented capability with its dependencies: connector scopes, selected
AI/model where needed, enabled permission, supported handler and processing readiness.
Local manual capture, evidence browsing and correction remain usable without AI.

For a future numeric implementation, use deterministic documented capability
weights and readiness factors for dependency health and data freshness. Count each
capability once; two providers offering the same outcome do not double its value.
Independent healthy alternatives can preserve availability. Show missing coverage
when only one of several sources works; do not imply complete mailbox coverage.
Keep the denominator stable within a published scoring version, covering implemented
capabilities in that version, and explain changes when that catalog changes.
Weights, freshness thresholds and score bands need a separate implementation plan
and tests; this design does not invent precise percentages or a productivity measure.

Show the reason for each contribution or reduction. Unknown or outdated health
cannot be called healthy. Distinguish connection reachability, data freshness and
successful end-to-end processing. A new successful health probe does not make old
data current. A connected source with no completed scan has unknown data freshness;
an intentionally paused schedule is visibly paused, not automatically failed.
If readiness cannot be established, show an incomplete/unknown score explicitly.

## Automatic health checks and recovery

Check expired/revoked credentials, failed synchronizations, unavailable selected AI
models and stalled document scanning. Use bounded per-user checks with timeouts,
backoff and last-checked timestamps. Expired check results age to unknown/stale.
Where scanner integration is only planned, label it planned rather than reporting
an invented heartbeat. A manual upload parser and a folder watcher are different
capabilities. Detect stalls from actual expected progress/leases, not idle time alone.

Each issue must show the affected source/model/job, plain-language explanation,
check time, impacted capabilities, last successful work and a relevant remedy:
reconnect/renew consent, inspect failed run and retry, choose/configure an available
model, or inspect/recover the stalled worker. Link to existing workflows. Keep
diagnostics sanitized and scoped to the authenticated user; never expose secrets.
Show recovery only when a new check or successful work establishes it.

Health checking must not ingest personal content, start a scan, expand OAuth scopes,
send private records to AI, silently change a model, or restart a worker. Reuse
existing configured permission/budgets for external probes; disclose any paid probe
before execution. Actual ingestion remains chat-requested or explicitly scheduled.

## Explain what a new connection unlocks

Before connecting, preview the useful outcomes and their prerequisites. After a
successful connection, compare effective capability availability before and after:
show **Newly available**, **Still needs setup** and **Already available** with reasons
and direct next actions. Distinguish enabled processing from completed discoveries.

For example, Gmail plus granted read scope, configured AI permission/model and a
supported discovery handler can enable requested purchase discovery. Connecting
Gmail alone must explain that discovery still needs setup and an explicit run or
schedule. Additional email coverage may improve reconciliation without proving
item identity. Subscription tracking is a future capability until its own supported
service exists; it cannot be claimed as unlocked merely by connecting email or a bank.

## Primary navigation docking

The navigation sidebar defaults to the **left** and can dock **left, right, top or
bottom**. Resize width on side edges and height on horizontal edges; offer pointer
interaction plus keyboard-operable docking and resize controls. Horizontal docking
must reflow navigation rather than rotate labels. Keep all destinations reachable
when space is limited, preserve the selected page and drafts, and avoid page overflow.

Remember position and dimensions per account in this browser, with safe bounds,
viewport clamping and Reset layout. On narrow screens use a compact accessible
navigation layout without overwriting the saved desktop preference. Coordinate
space when navigation and assistant choose the same edge, preserving a usable
content area, focus order and controls at zoomed and narrow sizes.

This navigation panel is separate from the existing contextual assistant, which
already docks at all four edges and resizes and defaults to the **right** (v0.49.0).
Preserve the assistant's existing saved layout and conversation behavior. Floating
windows and arbitrary panel arrangements are outside this scoped requirement.

## Acceptance for later implementation

- Power Center is directly reachable as a primary destination in both themes.
- Receipt discovery contributes more useful capability than account metadata;
  redundant connections do not inflate the same capability's score.
- Revoked credentials, failed runs, unavailable models, stalled supported scanners,
  missing checks, paused schedules and stale data have accurate distinct states.
- Each issue explains its actual impact and opens the correct recovery workflow.
- Connecting a service explains precisely what changed and what still needs setup;
  unsupported features never appear newly available.
- Health checks do not trigger ingestion or bypass configured AI/connector permission.
- Two users cannot inspect each other's health, capabilities, jobs or credentials.
- Navigation docks/resizes on every edge by pointer and keyboard, persists per
  account, resets safely and coexists with the assistant on desktop/narrow screens.

No application version, schema, dependency or running-installation change accompanies
this documentation update. Implement Power Center and navigation docking as separate
bounded releases after current-source review; do not prebuild future integrations.
