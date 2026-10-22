# From a saved note to an asset

In Chat, save a note, open its source, and choose **Suggest an asset from this
note**. Choose your OpenAI credential and Responses-compatible model, then choose
**Suggest asset**. This explicitly sends only that selected note (up to 4,000
characters) to OpenAI. External AI consent is required. The app's existing daily
20-request allowance, cancellation, timeouts and retry identity also apply; one
extraction uses at most one provider call. Model access is account-dependent and
has not been tested with a real key here.

The proposal persists privately without creating an inventory item. Review and
edit the item name, manufacturer, model, serial, statement type and exact quote.
Unknown identifiers stay empty. Choose **Check details and possible duplicates**
after editing. The server requires every nonempty identity value to appear in an
exact quote from the selected source. This is a structural evidence check, not
proof of the statement's meaning or truth; review the meaning yourself.

Choose an existing candidate as the same physical item, or explicitly create a
different item, then **Confirm asset**. Similar names/models alone never silently
merge items. A known manufacturer-scoped serial blocks creating another unit.
The duplicate check covers bounded name/alias, product-model and serial matches;
it cannot identify every differently described item. Candidates are owner-scoped
and rechecked at confirmation; changed matches require checking again.

Confirmation stores the human-reviewed fields and reconciles them in one PostgreSQL
transaction. Ownership remains **inferred**, not verified or proof of current
possession from a past purchase. Product links and original evidence use the
existing reconciliation ledger. Serial data remains in the structured observation.
**Reject proposal** keeps the note and adds no inventory record. Viewing and
reviewing an existing proposal need no AI connection. Reopen the conversation or
use **View asset proposal** on its evidence to find a persisted proposal again.
Lost-response retries preserve the same decision ID and cannot add another item.

This slice handles one physical item per saved-note revision. The extractor is
instructed to decline multiple items/units, gifts for others, sales, returns,
cancellations, payments, contradictory ownership and hypothetical purchases;
mentions remain outside inventory. Semantic classification is fallible and human
review is required. Prices, world dates, financial entries, quantities, upload
extraction, automatic inventory creation and a general asset dashboard are later.

A corrected note needs a new proposal from its current version. A stale proposal
can be inspected/rejected, but cannot be confirmed. Already accepted assets and
graph facts are not automatically rewritten by later text corrections. The current
increment has no user-facing undo for an accepted asset; the reconciliation service
retains its decision history for the later correction/review interface.

Migration `0008_asset_proposals` adds owner-constrained proposal/review records
without changing existing notes, chats, sessions, inventory or settings. Snapshots
include the table; `ProposalService.export_page` provides owner-scoped pages of 25
alongside the existing memory/reconciliation exports. No credentials are exported.
Typed MCP operations `asset_proposal_get`, `asset_proposal_preview` and
`asset_proposal_review` share the same service as Chat. The app model receives no
operational tools and cannot approve its own proposal. Source text never authorizes
a confirmation.

The existing adapter's strict output schema was checked against the
[official structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Tests use fixed synthetic outputs and no live provider requests. They cover quote
validation, isolation, CSRF, invalid output, durable usage, cancellation, concurrent
review/replay, rollback, identity choices, stale notes, migration and snapshot restore.


## Record if identity is clear (v0.26.0)

After reviewing the exact fields/quote and selecting your purchase or possession
statement, choose **Record if identity is clear**. The same transaction validates
the current source, checks identities and either creates a new physical item or
enriches one unique active manufacturer/serial identity. It requires no separate
same/different selection when the identity check is clear. No new AI call occurs.

A similar name/model, conflicting identifiers, prior exclusion/ownership correction
or conflicting serial history stays pending. The card preserves your edited fields,
shows candidates and a reason, and offers the existing explicit same/different
review. It creates no intermediate graph observation when returning a pending draft.
Repeated ambiguous checks are safe. Completed automatic actions are explicitly
labeled; source evidence and original candidate history remain intact. Connection
loss freezes the form and retries the same decision request.

This is a bounded first automatic-discovery slice for explicitly reviewed one-item
proposals, not unattended AI ingestion or multi-item auto-import. Selecting purchase
or possession and invoking the action is your statement about the reviewed item;
ownership remains inferred. Prices/dates are not inferred. Undo/correction uses
existing asset evidence/ownership controls. Current-source, owner, origin/CSRF,
request replay, receipt-overlap and original-file guards apply equally to `auto`
on the existing review HTTP/MCP contracts. Deleted PDF originals now block manual
single-item acceptance too, fixing the previous gap relative to receipt batches.


## Compare possible items (v0.27.0)

After a duplicate check, choose **Inspect** beside a candidate to view its private
source-backed identifiers and latest recorded corrections. Open a second candidate
to compare them side by side; opening a third replaces the oldest comparison.
Inspecting never selects an identity, edits records, merges items or calls AI.
Your explicit same/different decision and the server's current checks still apply.

The same comparison is available on receipt-line checks and identity review. Each
snapshot requests three sourced observations and three correction records through
the existing authenticated asset-detail read. It labels earlier/current evidence
associations, original quotes, unknown identifiers and current inventory status
without treating a past purchase as proof of ownership. Open the original,
identity or correction evidence directly. A notice identifies omitted history;
use Assets for the complete paged history. These are snapshots, so inspect again
if another operation changes the record before your final review.

Candidate buttons page in groups of five, with at most two open snapshots. Closing
or replacing a pending snapshot cancels its read, and late responses are ignored.
The component resets when the parent review/candidate context changes. Read errors
can be retried. Existing session/owner isolation applies; no new backend contract,
model tool, permission, migration, dependency or financial operation.
