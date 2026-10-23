# Add an asset yourself

Choose **Assets → Add asset**. Enter the name (the only required text field) and
optionally pick an **Asset type**; General item is the default. Add any known
manufacturer, model and serial number (a model or serial needs its
manufacturer). A chosen type shows its own optional fields in a separate
"<type> details" group below. Confirm **I currently own this item**, then save.
Missing identifiers, prices and dates remain unknown. No AI provider is required.

LifeGather saves your entered details as original manual evidence. Ownership and
profile fields are **stated**, not independently verified. Open the item’s evidence,
field history or graph to inspect the saved statements. Existing profile editing
and ownership corrections remain available.

If a similar record exists, inspect it and either add information to that item
or explicitly create a separate physical item. A matching serial blocks creating
another copy. Names and shared models alone never cause automatic merging. Items
with a current sold/returned/non-ownership correction require updating ownership
through the existing details/correction action first.

Manual entries use the same canonical identity bindings as discovery. A later
receipt with the matching manufacturer-scoped serial can enrich the same record.
Notes are retained as entered evidence, not automatically interpreted as facts.

If a save response is lost, **Retry same save** resends the original request ID
and payload. An already completed save does not reassert ownership after a later
sale or correction. Conflicting identities and invalid writes roll back atomically.

Authenticated HTTP operations are `POST /api/assets/manual/preview` and
`POST /api/assets/manual`. Equivalent MCP tools are `asset_manual_preview` and
`asset_manual_save`; clients supply an explicit declaration, candidate snapshot and
identity choice. These write tools are not in the app model’s read-tool allowlist.
The operations never use ambient browser context. No schema migration is needed.
