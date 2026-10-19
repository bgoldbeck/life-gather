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

Pre-merge verification: 434 backend / 188 frontend tests pass, strict mypy src/tests,
Ruff lint/format, Prettier, oxlint, TypeScript and both builds pass. Twenty-two new
backend tests cover atomic source/draft writes, invalid/unclear/maximum bounds,
quote/quantity consistency, foreign/deleted originals, corrected text, concurrent
saves, permissions, cancellation, exact replay, photo links and snapshot recovery.
Seven new UI cases cover explicit mode/selection, gates, upload reuse, current
conversation/draft, lost/pending retries and cached receipt display in Photos.
Two regressions reproduced cropped quotes hiding Qty2; same-line/repeated-match
checks now refuse that case without mistaking prices/dimensions/other lines for
quantities. Existing full receipt/money tests pass. Accepted history is preserved.
Browser verified original photo/transcription inspection and human confirmation of
three distinct units from two lines, with blank prices/dates. 390px DOM width has
no overflowing Chat elements. Composed synthetic feature smoke passes locally;
final Linux container and publication follow source merge. Graphify unavailable.

GitHub main advanced to 1d74414 with PR62 release tooling only. Preserve that
work, reconcile the changelog and run its offline publisher/Git fixtures before
final merge; application/version/schema did not overlap.

Reconciliation complete: merged current main 1d74414 into the feature and kept
both changelog entries. Git diff confirms backend/frontend trees exactly match
the fully tested feature commit 6c36ce4. Merged host tooling passes 24 offline
publisher cases and 15 temporary-Git source recovery cases. No runtime overlap,
version collision or migration change. Synthetic browser tab/server closed and
viewport reset. Final feature/container smoke passed locally; release size before
build: existing image 81.4 MB compressed content / 347 MB unpacked.
