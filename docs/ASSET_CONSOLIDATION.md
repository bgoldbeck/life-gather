# Reversible asset consolidation

Use this when two records describe **one physical item**. Different units of the
same product remain different assets. The app never decides identity from a name.

In Assets, open **Compare complete current records**, select the other record and
inspect its evidence. Choose the primary record in **Consolidate these records**,
then select **Preview consolidation**. Review the refreshed comparison, supply an
explanation and explicitly confirm that both records describe the same physical
item. **Confirm consolidation** saves that identity decision.

## What changes

Current inventory and searches show one primary item. Either original ID opens the
current combined detail, which identifies both original records and links their
evidence. Galleries, Profiles, field history, graph navigation, sourced chat recall
and future receipt matching use that same identity. An identity choice does not
independently verify ownership, specifications or other claims.

No source, original entity or fact version is deleted or rewritten. Statements
retain their original subjects, status, dates, evidence and correction history.
Conflicting values remain separate; choose a statement explicitly when correcting
it. Graph endpoints project the current identity with original-ID metadata; original
fact reads retain original IDs. Historical recorded-time reads use the identity
known then. Old saved conversation answers remain historical records.

Purchases and units keep their identities. Whole-line and order totals remain
separate source claims; consolidation does not add, divide or allocate money.
Existing photo links are projected together without duplicating originals. Explicit
removal from a combined gallery removes its member links while retaining the file.

## Reversal and retries

The combined detail offers **Reverse consolidation**. Supply an explanation and
explicitly confirm separation. Both original records reappear under their prior
identities, with a recorded reversal and preserved original evidence.

**Consolidation history** shows active and reversed identity choices on each
affected record, with paged access to both original explanations. An explicit
ownership change on the combined item also advances action-owned status statements
on both originals; independent conflicting statements remain visible.

Reversal requires the affected comparison, fact/action history and identity history
to remain unchanged. Later facts, receipt decisions, profile corrections, gallery
changes or other dependent changes can block reversal. Inspect current history;
the app will not overwrite later work. A new preview after reversal cannot reuse an
older preview token. Unrelated records do not invalidate reversal.

After a lost response, keep the frozen selection and choose **Retry same request**.
This reuses the request ID and cannot apply the change twice. A saved change whose
reload fails offers a read-only **Reload record** action.

## Scope and implementation

This release handles two unconsolidated assets, with one primary. Bulk operations,
active groups larger than two, consolidation chains and unattended AI approval are
excluded. Existing batch evidence moves require reversal of consolidation first.
Sibling receipt/discovery units, a current replacement relationship, and conflicting
manufacturer/serial/VIN identities must be corrected separately before consolidation.

Preview reuses the complete current comparison and all its collection/byte limits,
plus at most 500 relevant fact revisions, actions and identity choices per category.
Overflow refuses the whole operation. Apply verifies the preview in a serialized
transaction; concurrent overlapping groups cannot share an active member.

Migration `0023_asset_consolidation` adds owner-constrained history and two active
membership rows. Framework-independent services back authenticated HTTP and typed
MCP operations: `asset_consolidation_preview`, `asset_consolidate` and
`asset_consolidation_reverse`. HTTP writes require same-origin session/CSRF; MCP
retains its existing session/CSRF transport authority. App models receive no new
write tools, and source text cannot authorize a consolidation.

Whole-database snapshots preserve history, active membership and retries. Personal
record format `lifegather-records/2` adds `asset_consolidations`; membership rows are
a derived current index, while the exported history describes both original IDs and
reversals. This is still a portability file, not an import or backup protocol.
