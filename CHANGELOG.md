# Changelog

## 0.5.0 — 2026-10-18

- Browse/search private inventory and include historical asset records.
- Inspect sourced item details, inferred ownership, decision/fact history and
  exact original evidence with bounded paging. No schema or data migration.

## 0.4.0 — 2026-10-18

- Propose one physical item from a selected saved note using bounded OpenAI
  extraction; no inventory changes occur until explicit human review.
- Review/edit exact evidence and supported identifiers, check private duplicate
  candidates, and explicitly choose the same or a different physical item.
- Preserve original proposals, human-reviewed fields and source evidence. Reject
  without creating inventory; retry confirmation safely after lost responses.
- Migration `0008_asset_proposals` adds owner-constrained proposal history without
  rewriting existing notes, accounts, sessions, chats, settings or inventory.
- Block stale-note confirmation and duplicate manufacturer-scoped serial creation;
  keep ownership inferred and missing prices/dates unknown. One item per note;
  broader extraction, accepted-asset correction UI and uploads remain later.

## 0.3.0 — 2026-10-18

- Add explicitly enabled, one-click test login with a shared test workspace and
  persistent warning banner. Normal sign-in remains protected and separate.
- Display the application version on the login screen and inside the app, with
  the exact Git revision when embedded by the release process.
- Establish one application version source and verify package/API/container
  metadata agree. Older images retain their original metadata.

This is the initial visible versioning baseline. Source completion does not imply
that the corresponding Docker image has been published or deployed.
