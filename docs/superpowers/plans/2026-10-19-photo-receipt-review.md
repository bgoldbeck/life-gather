# Reviewed multi-item receipt photos

Baseline: clean/fetched main 916d178, v0.41.0. Separate release-source-recovery
branch is a tooling-only plan; no overlapping runtime work. Graphify unavailable.

Add an explicit Chat action for multi-item receipt photo reading. Reuse the
private uploader/picker and existing receipt review, exact quantity/source checks,
8-line/20-total-unit bounds, typed-money workflow and manual inventory gates.
The first vision result retains one unverified transcription plus a receipt draft
atomically, with no automatic inventory/financial writes. Preserve current single
photo behavior and all provider permissions/budgets/cancellation/safe retries.
For already transcribed photos, reuse a saved receipt review; otherwise extract
from the current transcription after rejecting any active single-item proposal.
Never overwrite an original transcription or bypass review mutual exclusion.
Deleted/foreign originals and stale revisions remain refused. Keep the original
photo/source connected through receipt review and subsequent accepted items.

Validate new input/schema bounds, bad quantities/quotes/ownership, atomic rollback,
mode reuse/conflicts, corrected sources, private HTTP/MCP review, exact replay,
cancellation/deletion races and migration/snapshot compatibility. Add UI interaction
coverage for explicit mode/selection, saved draft/review, upload/no-eager AI,
consent/model/budget gates, retry bodies and context changes. Run all strict checks,
synthetic browser and Linux smoke, then release v0.42.0 through the standing
source/GHCR workflow. No schema migration, dependency or live provider call needed.
