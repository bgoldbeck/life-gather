# Start bounded email evidence scans from Chat

Baseline: clean/fetched main e1bf29b, v0.42.0. No competing application work.
Scope the first Chat scan action to existing Gmail text-evidence imports only;
AI purchase discovery and free-form agent planning remain separate. Reuse typed
GmailScanConfig, private mailbox permission, the durable queue/worker and Scans
progress/cancellation. Let users deliberately choose account, past dates, optional
query and 1..50-message cap, then start without another confirmation card. No AI
connection or budget is needed for text-evidence import; it never creates inventory.

Persist queue creation and the completed Chat result in one domain transaction
against the pending authenticated Chat request. Stable request identity reuses the
same job, changed arguments conflict, cancellation that wins first creates no job.
Preserve old Chat request fingerprints when the new optional scope is absent.
Untrusted notes, model output and ordinary text/Ask requests cannot enqueue work.
The Chat result links to the existing owner-scoped Scans detail/progress view.
Leaving Chat does not cancel the independently queued job. Preserve unsent drafts,
exact pending/uncertain retry arguments and context read cancellation.

Acceptance: owner/foreign/disconnected mailbox and invalid scope; no provider call
or AI budget use on enqueue; atomic rollback/replay/concurrency/cancellation and
snapshot recovery; existing Chat replay compatibility. UI: explicit account/scope,
no eager enqueue, AI-independent launch, frozen retry body, current conversation,
draft/context preservation and exact job navigation. Verify existing scan service,
worker/permission/schedule behavior, full strict tests, synthetic browser and Linux
smoke. Release v0.43.0 through the standing source/GHCR workflow. No schema or new
dependency, live mailbox/model request, recurrence or deployment change.
