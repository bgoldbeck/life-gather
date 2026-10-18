# Private asset browser

Assets lists active inventory by default, with bounded case-insensitive name
search and pages of 25. Include historical records to inspect physical-item
records whose discovery decisions were undone or whose ownership was excluded.
Inventory means an active sourced reconciliation binding; it is not independent
verification of current ownership from a past purchase.

Open an item to inspect sourced manufacturer/model/serial observations, their
exact quotes, decision reasons and preserved fact versions. Conflicting sources
remain separate observations. Recorded time and world-valid dates are displayed
separately; missing prices and dates stay unknown. Original source inspection is
authenticated and paginated, including superseded notes used by old decisions.

The framework-independent `AssetService` backs thin authenticated HTTP routes and
typed `assets_list`/`asset_detail` MCP operations. All queries, cursor validation,
fact evidence and source inspection are owner-scoped. No model access is required.
This increment is read-only and adds no schema migration. Decision correction,
photos and the review queue follow in their separately tested increments.
