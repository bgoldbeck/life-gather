# Compare current item records

In Assets, open an item and expand **Compare complete current records**. Find and
explicitly select another existing item, then compare. Historical items are included
in the chooser. No provider connection is needed and no data is written.

The comparison shows current statement versions, their evidence and world/recorded
dates; incoming and outgoing relationships; alternative names; gallery link metadata
including deleted originals; current discovery units; linked receipt line claims;
and related purchase evidence. Source buttons open original evidence and identify
later note corrections. Inventory membership remains potentially inferred. A large
integer literal retains its exact display even beyond the browser's number range.

Differing statements with overlapping or unknown dates, a replacement relationship,
different physical units from one discovery/purchase line, and competing current
order/receipt totals receive inspection warnings. Warnings do not establish that
records are duplicates. Unknowns and conflicting sources are preserved. Receipt
amounts describe whole lines and purchase amounts remain separate source claims;
the comparison does not sum, allocate or divide them. A shared purchase evidence
association appears once in the related-purchase section.

All collections come from one PostgreSQL read snapshot, including the existing receipt
reader. Refresh after changes. Closing/clearing, selecting another target, changing
the search or navigating to another item prevents old responses from reappearing.

Limits apply across the pair: 50 statement versions, 100 evidence links, 100 aliases,
40 photo links, 40 discovery associations, 50 purchase evidence associations, 200
sources and 30,000 serialized UTF-8 bytes. Receipt claims are additionally limited to
20 associations per item (40 combined). If any bound is exceeded, no partial record
details are returned. All counts in an incomplete comparison are lower bounds, not a claim
to have counted or inspected every historical row. Use individual detail/history
views for larger records. Limits fit the existing MCP response contract.

Scope excludes superseded fact versions, earlier reconciliation/action history,
full note revision text and original image bytes. Those remain available through
their existing private inspection/history interfaces. Photo links alone do not
support claims; deleted originals are not resurrected. This comparison makes no
merge, preview-token authorization, ownership change or automated correction.
Complete-record consolidation and reversal remain separate work.

Authenticated HTTP: `POST /api/assets/comparison` with `asset_id` and
`target_asset_id`. Read-only MCP: `asset_record_comparison`, same arguments and
service. Both IDs must be distinct existing physical items owned by the acting
user. Request bodies retain the existing 32 KiB cap; callers cannot raise response
or collection limits. No migration, dependency or live provider call is introduced.
