# Sourced replacement links

On the original item's Assets screen, open **Connect a replacement item**, find
and explicitly choose the distinct existing physical item that replaced it.
Compare the records if needed, explain the relationship in your own words, and
optionally enter a known replacement date. Save with **Record replacement link**.
The original item can be historical, sold or returned; search includes historical
records. Create a missing item through the normal reviewed discovery workflow first.

The service records a `stated` graph assertion:
`original item — replaced_by → replacement item`. Its evidence is the exact
explanation, preserved as a private original conversation episode. The optional
date becomes the assertion's valid-world start and episode event date. Unknown
dates remain unknown; future or invalid dates are refused. This is the user's
statement, not independent verification or automatic identity matching.

Both records retain their own receipts, unit mappings, purchase amounts, aliases,
photos and ownership facts. Neither item is deleted, combined, sold or added to
inventory by this action. Existing contradictory statements remain visible.
Duplicate active links to the same target are refused; identical request retries
return the original result. Other distinct replacement statements can coexist.

The graph shows the sourced relationship, and both item histories show the action.
The receiving item's own write head is unchanged. On the original item, the latest
own replacement action offers **Withdraw latest replacement link**. Explain the
mistake, then withdraw the still-current statement. Withdrawal supersedes that
relationship only, records its own original explanation and audit action, and
preserves the earlier fact, evidence and valid-world dates for recorded-time reads.
It removes the superseded relationship from current graph connections.

Withdrawal is refused if another own correction followed the original action or
the relationship was manually corrected. It never rolls back later ownership or
receipts. For older links, inspect history and use the existing fact-correction
service; a general UI for choosing any earlier assertion is not part of this slice.

HTTP: `POST /api/assets/replacements/record` accepts `asset_id`,
`target_asset_id`, `expected_action_id`, `request_id`, `note`, and optional ISO
`event_date`. `POST /api/assets/replacements/withdraw` accepts `action_id`,
`request_id`, and `note`. Both use the existing owner session and CSRF checks.
MCP exposes the same domain service through `asset_replacement_record` and
`asset_replacement_withdraw`, requiring a direct human choice. Neither tool is
available to the app model. The append-only asset-action ledger, original sources
and assertion history survive snapshot recovery with exact retry identities.

No schema migration, dependency change, external provider call or redeployment.
