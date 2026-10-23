# Research-save retry receipts (v0.84.1)

Baseline: main b728995, v0.83.0, migration 0034. Review reproduced two faults: changing the asset while reusing a request ID returns the earlier save, and replaying a deduplicated save after removal creates active evidence again.

Scope: persist an owner-scoped receipt for every accepted research-save request, including duplicate saves. Bind the exact original turn, URL and requested asset to the request ID. Replays return the original finding's current removal state without writing new evidence, even after conversation deletion. A new explicit request may save again. The UI must explain removed receipts and offer an explicit new save. Retain a conservative compatibility path for pre-receipt findings.

1. Write and observe failing service and UI regressions for conflicting assets, deduplicated save/remove/retry and removed acknowledgments.
2. Add migration 0035 and typed receipts; serialize receipt and finding in the existing transaction. Apply owner foreign keys and RLS. Preserve receipts in records format 6 and accept formats 4 and 5 on restore.
3. Implement the UI state, add replay/restore/owner tests and update version, capabilities and release notes.
4. Run focused then complete backend/frontend checks, archive/recovery and browser journeys; review the diff, refresh Graphify, repeat the remote clash check, release the tested branch through PR and publish clean main using the existing launcher.

Acceptance: exact retries have one result; changed inputs fail; removed evidence never reappears from a replay; deduplication requests retain their own receipt; removal state is visible; explicit save-again works; receipt ownership and archive/recovery boundaries hold. No provider calls or personal evidence are needed.

Overlap check: origin/claude/memory-deletion (05fd8f5) currently changes only docs/MEMORIES.md and proposes v0.84.0 without a migration. Preserve it; this patch does not implement memory deletion. Recheck code, format, migration and version consumers before merging.

Review focus: consolidation/reversal, old receiptless archives, missing conversations, concurrent duplicate requests, cross-account foreign keys/RLS, failed transaction rollback and browser lost replies. One active implementation worktree; review main is frozen for the baseline publisher. Review inline under repository's no-agent workflow.

Reconciliation: main advanced to 3a2dfec / v0.84.0 (PR121 Power Center0.83.1 and PR122 memory deletion0.84.0). Preserve both, release this fix as0.84.1, retain migration0035/format6. Re-run source consumers, quality, complete suites and browser journeys on this baseline. Old incomplete test runs were deliberately canceled before build/upload. Original WIP is recoverable in the recorded Git stash and outside-repo patch.
