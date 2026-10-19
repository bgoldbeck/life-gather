# Reviewed discovery-evidence batches

From an item's **Move several discovery sources** section, find an existing
destination and compare its evidence. Preview every association, inspect the
quoted passages and receipt unit numbers, explain the choice, then explicitly
move the previewed evidence. A product name alone never authorizes a move.

The slice moves all **1–5 current discovery associations** for the selected item
in one database transaction. It refuses an empty or larger batch rather than
silently moving only part. For a multi-unit receipt, only the selected physical
item's binding moves; sibling units keep their ordered records. A destination
already representing another unit of the same observation is refused. Receipt
totals remain whole-line claims and are never divided or duplicated as unit prices.

Original episodes and all earlier decisions remain. Discovery-owned inferred
ownership and product facts follow the new bindings. Notes, photos, aliases,
manual ownership statements, other facts and relationships stay on their original
records; neither record is deleted. **This is not whole-record consolidation.**
Conflicting manual statements are preserved rather than silently resolved.

Preview fingerprints include both items' own correction heads and every affected
current decision and unit mapping. Apply rechecks the entire snapshot in the same
serialized write transaction. A change invalidates the preview. Browsing a preview
does not write sources, decisions or audit events. Passage excerpts are limited to
400 characters with an explicit shortened marker and a link to the original source.

On the original item, **Reverse latest evidence batch** restores the recorded
unit mappings with a new explained decision for each observation. It requires
the original batch to remain that item's latest own correction, the destination's
own correction head to remain unchanged, and every moved decision to remain
current. If any guard fails, the entire reversal is refused; use the individual
correction workflow after inspecting history. Unrelated manual facts are never
rolled back. There is no automatic repeated undo/redo chain.

Lost responses retain the exact request and freeze draft inputs for safe retry.
Successful writes whose reload fails offer a read-only reload. A stable request
ID cannot be reused with changed arguments. Replaying either operation after
later changes returns its original result without performing another write.

Private HTTP endpoints:

- `POST /api/assets/evidence/preview`: `asset_id`, `target_asset_id`.
- `POST /api/assets/evidence/move`: both IDs, `preview_token`, `request_id`, `note`.
- `POST /api/assets/evidence/restore`: `action_id`, `request_id`, `note`.

All require an authenticated owner; writes also require the existing same-origin
CSRF session. MCP tools delegate to the same service and transport authority.
They require direct human choices and are excluded from the app-model tool set.
The existing append-only asset-action ledger stores the bounded reversal snapshot;
asset browsing exposes its association count rather than repeating large snapshots.
Exports retain the complete ledger; database snapshots preserve replay and reversal.

New batch explanations and audit entries are timestamped no earlier than all
changed decisions and both item records. Reversal advances the source item's
correction history even if the wall clock stalls or moves backward. Historical
fact reads at the correction timestamp therefore include its effects. Existing
stored episodes and timestamps are preserved rather than rewritten.

No schema migration or dependency change. No external model call, unattended merge,
connector ingestion or deployment change is introduced.
