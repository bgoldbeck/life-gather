# Power Center implementation claim

Claimed 2026-10-20 on `codex/power-center`, baseline main `7fda8ed`,
application 0.57.0 / migration 0025. No open PRs at kickoff; existing remote
feature refs concern already delivered unrelated capabilities. One implementation
checkout, no subagents. Implements the existing Power Center design; navigation
docking is already delivered and is not reimplemented.

## Intended behavior

- Primary Power Center destination with private source cards, supported capability
  catalog, explainable versioned readiness, actionable health and freshness.
- Framework-independent service and authenticated MCP/HTTP adapters; existing
  settings, Gmail consent, scan jobs/schedules and provider preferences remain the
  source of truth. No duplicate credential store or ingestion scheduler.
- Bounded automatic local checks and manual refresh; saved credentials are only
  configured, never proof of provider/model reachability. Recent successful work
  establishes observed health. Unknown/stale observations stay explicit. No paid
  probes, private-content transmission, ingestion or expanded consent from checks.
- Diagnose failed jobs, expired processing leases, disconnected mailboxes,
  missing AI permission/configuration, budget limits and paused schedules; link to
  existing remedies. Distinguish observed health from data freshness and scope.
- Explain newly available, still-needs-setup and already-available capabilities
  after connection changes, without claiming discoveries or future integrations.
- Responsive accessible light/dark UI with filters and explicit loading/error,
  empty and incomplete states. Preserve assistant drafts and navigation controls.

## Implementation and acceptance

1. Inspect graph/source and existing provider, scan, mailbox and usage contracts.
2. Add deterministic bounded owner-scoped status service and typed response;
   expose via authenticated MCP and thin UI adapter. Prefer derived observations
   to new persistent health state; add migration only if schema actually changes.
3. Build Power Center UI, navigation and connection-change explanations; document
   scoring version, evidence windows, costs and supported versus planned features.
4. Verify service freshness/scoring, owner isolation, MCP/HTTP authorization,
   no secrets/no provider calls/no scan enqueue, job failures/stalls and paused
   schedules; UI navigation, filters, refresh/errors and stale callback safety.
5. Run backend pytest/Ruff/strict mypy from backend and frontend tests/lint/types/
   formatting/build from frontend, package build, synthetic browser QA and
   isolated container smoke. Refresh local code-only Graphify and HTML.
6. Release 0.58.0 with changelog/docs; fetch/reconcile main and review intended
   diff, commit/push, PR/tested-head merge, verify closed and clean main, delete
   merged feature branches. Build linux/amd64 on clean main, smoke, publish
   immutable SHA and latest GHCR tags, verify remote revision/digest. Report image
   size before build and upload. No running-server redeployment.

If fresh baseline reveals overlapping work, preserve it and reconcile only the
missing behavior. GitHub Actions stays disabled. Final release records actual
checks and limitations rather than treating mock tests as live verification.
