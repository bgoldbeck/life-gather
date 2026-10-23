# Source erasure

Date: 2026-10-23. Status: chosen by Lisa from the remaining-work list; built in v0.96.0 (see [Source erasure](../../SOURCE_ERASURE.md)).
Baseline: GitHub main aa2093d, application 0.95.0. No other branch or open PR touches deletion. Builds on selective deletion (v0.76.0), memory deletion (v0.84.0) and account deletion (v0.87.0).

## Intent

Let a person erase one source and everything LifeGather made from it, in their own account only. Memory deletion (v0.84.0) keeps records made from a memory; account deletion removes everything. Erasure sits between them: the source's rows are deleted, not tombstoned.

## First slice

Two kinds of source:

- **A Gmail connection.** Every email memory its scans saved (`gmail-memory:` and `gmail-attachments:` namespaces), documents made from its attachments (rows and stored files) and their reviewed text, discovery caches, scan runs, run items and schedules for it, its saved credential and the connection itself.
- **One finished scan run.** The memories the run saved, attachment documents from them, and the run with its items.

Everything derived is found by following the database's own foreign keys from the erased rows (read from `pg_catalog`, as account deletion does), so new tables are covered without a list to maintain:

- Any row that references an erased row is erased.
- A fact whose every piece of evidence is erased is erased.
- An entity (asset, product) created from an erased source survives when a source you keep also has evidence about it; it is then attributed to the earliest such source. Otherwise it is erased with its facts, photo links, maintenance and research.
- A surviving correction of an erased fact keeps its own evidence and becomes the start of its history; a surviving fact that an erased fact had superseded becomes current again. Revision chains (purchase evidence, maintenance, decisions, asset actions) are detached the same way.
- Search entries and audit receipts for erased rows are removed; one content-free `source_erased` receipt with counts is written.

The UI previews counts per kind first. Erasing requires the preview's fingerprint, so anything that changed in between refuses with "preview again". Active scans refuse. Stored files are removed before the rows (a storage failure changes nothing).

## Limits

Chat conversations that quoted an erased email are not changed (delete them in Chat). Google's grant is not revoked at Google. Existing exports and backups are unchanged. No MCP or model erasure tool and no migration.

## Acceptance

Tests: mailbox erasure removes every derived row and file and nothing of a second mailbox or account; shared product/asset survives when another source has evidence; un-superseding; stale preview refused; active scan refused; export and restore still work afterwards; HTTP auth/CSRF; UI preview and confirmation.
