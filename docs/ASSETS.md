# Private asset browser

Assets lists active inventory by default, with bounded case-insensitive name
search and pages of 25. Include historical records to inspect physical-item
records whose discovery decisions were undone or whose ownership was excluded.
Inventory means an active sourced reconciliation binding or current user-stated
ownership without a conflicting current exclusion; it is not independent
verification of current ownership from a past purchase.

Open an item to inspect sourced manufacturer/model/serial observations, their
exact quotes, decision reasons and preserved fact versions. Conflicting sources
remain separate observations. Recorded time and world-valid dates are displayed
separately; missing prices and dates stay unknown. Original source inspection is
authenticated and paginated, including superseded notes used by old decisions.

The framework-independent `AssetService` backs thin authenticated HTTP routes and
typed `assets_list`/`asset_detail` MCP operations. All queries, cursor validation,
fact evidence and source inspection are owner-scoped. No model access is required.
The initial browser was read-only and needed no migration. Photos and the review
queue follow in their separately tested increments.

## Correction and ownership history

Open **Make a correction** on the item. Choose an ownership statement, undo a
single-item confirmation/association, or explicitly move its evidence to an owned
existing item or a different physical item. Supply an explanation. The app never
deletes or globally merges entities when reassociating evidence. Multi-unit
decisions need a later unit-aware correction interface and are refused here.

Sales/returns/no-longer-owned statements remove the item from current inventory;
**Include historical records** keeps it inspectable. A later **I own this item**
statement restores current inventory where there is no independent conflicting
ownership correction. Omitting the event date leaves it unknown. Dates cannot be
in the future or precede the last dated ownership event. Where event dates are
known, closing and replacing fact versions preserves the earlier world interval.
Both recorded and world-valid times remain available in fact history.

Every change records an immutable explanatory source, an append-only action and
the resulting fact/decision versions in one serialized transaction. Stale item or
decision versions conflict; identical request retries return the recorded result,
even after subsequent actions. Correction explanations retain authenticated item
context in recall while their original text stays unchanged. This is user-stated
evidence, never independently verified truth. Model tools cannot approve changes.

Migration `0009_asset_actions` adds owner-constrained actions and preserves prior
data. Snapshots include the records; `ActionService.export_page` provides private
pages of 25. Asset detail correction history is paginated. Undoing a mistaken sale
means recording a new ownership statement; undo confirmation/association reverses
the selected reconciliation decision and can return it to unresolved review.
