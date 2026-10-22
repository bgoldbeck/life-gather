# Evidence reconciliation: first backend slice

The framework-independent `ReconciliationService` accepts structured synthetic discoveries over existing private sources. It does not scan email, parse receipts, call an AI provider, or expose a new HTTP/MCP/UI endpoint. The [saved-note asset proposal flow](ASSET_PROPOSALS.md) now supplies one human-reviewed item through thin HTTP/MCP adapters. Its extractor receives no operational tools or credential access.

## What is kept separate

Migration `0004_reconciliation` adds owner-scoped purchases, purchase lines, observations, decisions, unit bindings, and review candidates. Product models and individual physical assets are separate memory entities. Each observation retains its original source, local item key, exact input, and fingerprint. Decision-owned graph facts link an asset to its product model and mark ownership as inferred; purchase/order metadata is retained in the reconciliation ledger, not rendered as graph nodes yet. No prices, financial transactions, delivery claims, warranty claims, or invented dates are recorded.

All cross-record links use owner-constrained foreign keys. Source ownership, quote membership and identity-field presence are checked before committing. A quote containing an identifier is only a structural evidence check; it does not prove semantic truth. Future extraction must distinguish purchases, mentions, gifts, cancellations, returns, and payment-only data correctly. Statements cannot establish item contents.

## Matching and quantities

- A source/item replay returns its current decision. Different input under the same key is a conflict requiring a new source revision.
- Reliable order identity includes retailer, account scope, order ID, line ID, and unit ordinal. Retailer/product labels use normalized text; account, order and line identifiers are case-sensitive and must come from a consistent connector/import scope.
- Serial identity needs manufacturer context and a single unit. Serial values remain case-sensitive. Product/serial conflicts or competing identity targets require review.
- Name/alias and manufacturer/model similarity supply candidates, never proof that two physical objects are the same.
- Clear new purchase/possession observations create inferred inventory automatically. A different anchored order can distinguish another unit of the same product; an unanchored candidate requires review.
- Quantities must be explicit integers from 1 to 20. A line of quantity two maps to two distinct physical items. Replays preserve the unit mapping. This slice expects the full line quantity; partial shipments or changed quantities go to review. Multiple serials on one line are deferred.
- Mentions and payments create review work without inventory. Existing negative ownership assertions, conflicting identifiers, or previously excluded identities cannot be silently overridden by a later matching source.

Matching reads are bounded; more than 100 candidate/identity evidence rows require review instead of making a truncated automatic decision. Completely unrelated labels without a shared alias, model or reliable identifier cannot be resolved automatically; users can associate the evidence explicitly.

## Review and correction contract

| Method | Behavior |
| --- | --- |
| `discover(actor, DiscoveryInput(...))` | Create, enrich, or persist review work atomically |
| `get(actor, observation_id)` | Current decision, reason, candidates and unit targets |
| `resolve(actor, observation_id, expected_decision_id, asset_ids=...)` | Associate one distinct existing asset per unit; `None` explicitly creates different items |
| `dismiss(...)` | Exclude this observation from inventory; other corroborating observations remain active |
| `undo(actor, decision_id)` | Restore the preceding decision through another version; undoing the first automatic decision produces review work |
| `reviews` / `inventory` / `history` | Owner-scoped bounded pages; inventory is the active discovery bindings, including inferred items |
| `export_page` | Owner-only purchase/line/observation/decision/binding/candidate pages, excluding credentials and authentication |

Changing a decision requires its expected current version; conflicting stale actions fail. Repeating the same change returns that action's recorded successor, which may itself be historical after further changes. Use `get` for the latest state. Unresolved review is the Not sure state and persists across retries/restarts.

Undo and reassociation retire only facts owned by the affected decision and write fresh versions at a consistent system timestamp. Original entities, sources, independent facts, and predecessor decisions remain available. This is evidence reassociation, not a destructive general-purpose merge or redirection of all arbitrary graph links. General entity consolidation and per-item return/cancellation workflows remain later work.

List limits are 1–100 (default 25), with at most 20 units per decision. Pass the last inventory asset ID, review observation ID, or history decision ID as the corresponding cursor. History is ordered by recorded time and ID; other pages use stable UUID ordering. Exports use the returned `next_cursor`. Pages are live queries, not a fixed transaction-wide export snapshot. Combine reconciliation exports with memory exports when exporting the complete domain record.

## Transactions, migration and recovery

A serialized PostgreSQL transaction covers the decision, purchase/unit metadata, memory entities/facts/evidence, search index updates, and audit records. Repeated or concurrent imports cannot double-create an observed unit. Exceptions roll back all derived writes. Migration 0004 extends the previous schema without rewriting existing accounts, sessions or memories. An already running/published container does not acquire these changes until a separately approved rebuild.

The existing operator-only database snapshot includes this ledger. Restore tests verify decisions and inventory survive reopening the snapshot. Keep the vault key separate as described in [private settings](PRIVATE_SETTINGS.md). No restore, build, image upload, or provider operation runs automatically.

The [implementation plan](superpowers/plans/2026-10-17-reconciliation.md) records this slice. Tests use synthetic sources and cover source order, quantities, duplicate/concurrent ingestion, correction/undo, excluded identities, ownership conflicts, direct database owner constraints, private export, migration preservation, rollback, clock reversal, and snapshot restore.


## Individual unit correction (v0.28.0)

From Assets → Make a correction → Move evidence to a different item, choose a
current decision and an existing target. For quantity 2–20, the displayed unit
number identifies this asset’s binding. Only that unit changes target; all sibling
ordinals and targets stay intact in the successor decision. Original source and
predecessor decisions remain. A target already used by a sibling is refused.
The typed line total remains the total for the entire line, never a per-unit price.

Supply an explanation and the current action/decision versions. Competing sibling
changes make the old decision stale. Safe retries return the recorded result, even
after a later reversal. To reverse, open the new target and move its current unit
back to the original historical asset. Whole-line undo and creating just one new
unit within a multi-unit line remain outside this slice. This does not merge whole
records or move unrelated evidence, photos, manual facts or ownership statements.
No schema or request-field changes; existing private HTTP/MCP operation is reused.


## Current inventory and ownership dates (v0.29.1)

`inventory` / MCP `discovery_inventory` lists active discovery bindings after
filtering currently valid negative ownership statements. The asset screen and
automatic matcher share the same current-world date conditions: valid-from is
inclusive, valid-to is exclusive, null boundaries are open, and superseded facts
are excluded. A currently valid negative statement requires identity review even
when it has an end date; a future or ended interval does not block current matching.
Historical bindings and facts are retained; explicit buyback corrections restore
current inventory. Discovery inventory remains discovery-bound, while Assets can
also include separate explicit stated ownership. Filtering occurs before paging.


## Inspect evidence moves (v0.30.0)

The asset correction form distinguishes decisions by ID, observed name and unit,
shows the exact selected source passage, and opens its original evidence. Search
for targets, then inspect up to two records, including the source or possible targets, using
the same bounded candidate snapshots as Review. Inspection never chooses a target;
changing a search or replacing results clears the previous selection.

Both original and receiving items show reassociation explanations in correction
history. Incoming entries name the original item, link to the exact correction,
and support private history pagination. These entries are historical movements,
not claims that the association is still current. Use current sourced decisions to
inspect present associations. Incoming reads do not advance the receiving item's
own action head, so later ownership corrections retain their normal version guard.

New actions retain actual targets even when the user creates a different single
item. Existing actions with explicit targets work immediately. Older actions that
created a new target without storing its ID are not backfilled; inspect them from
the original item's preserved history. No historical source is rewritten and no
migration is needed. Whole-record merging, photo/manual-fact relocation and a bulk
consolidation operation remain outside this increment.
