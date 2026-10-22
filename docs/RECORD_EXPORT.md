# Download your private records

In **Settings → Download your records**, select **Download records (JSON)**.
The app prepares one consistent copy of your records and starts a file download.
For original photos/documents as well, opt into the [personal ZIP archive](PERSONAL_ARCHIVE.md).
No AI connection, vault key or provider permission is needed. Nothing is uploaded
to another service or changed in your workspace. Keep the downloaded file private:
it preserves your saved content, including anything sensitive you put in a note
or conversation.

This is a structured records copy for portability and inspection. It is **not a
complete backup**, and there is no import/restore action. JSON contains metadata;
the ZIP option adds active original photos/documents, or download them individually
through their existing file views. Installation owners can use
[encrypted operator recovery](OPERATOR_RECOVERY.md) to coordinate the whole
database, original files and configuration/key backup.
Never substitute a personal export for a tested installation backup.

## Contents and limits

The export includes original source text; entities, aliases, facts and evidence;
original and superseding corrections; review decisions and distinct purchased
units; reviewed receipt/purchase claims; asset-action history; conversations and
their saved turns; photo metadata/gallery links; and document format/metadata/extracted text.
Manual maintenance tasks and all their sourced revisions are included as well.
Historical, inferred, unknown and unverified entries keep those statuses. A record
in this file is not automatically a verified fact or a current inventory item.

Original image/preview/document bytes are omitted, including deleted originals. Metadata
retains deletion markers. Extracted document text that was removed on deletion is
not recreated. Previously saved source evidence follows the existing preserved
history rules. Credentials, sign-in/account records, settings, mailbox connection
configuration, scan jobs/schedules, processing caches and search indexes are also
excluded. The file itself lists these exclusions.

Downloads are limited to **10,000 rows across all included collections** and
**16 MiB of complete UTF-8 JSON**, including metadata. One source can have several
facts/evidence/review rows, so the row limit is not an asset count. If either limit
is exceeded, the server refuses the entire download. It never emits a partial
file labeled complete. Ask the installation owner for a backup if these bounds
are insufficient. A failed download does not change data; retry explicitly.

Change origins from the current field-history workflow are retained in each audit
row's `provenance_json`. Unknown legacy attribution remains null; the export does
not guess who made an old change or relabel its confidence.

## File format

The envelope identifies `format: "lifegather-records/5"`, `application_version`,
UTC `snapshot_at`, purpose, exclusions, per-collection `counts` and `total_records`.
`collections` contains arrays with these stable names:

| Collections | Meaning |
| --- | --- |
| `asset_types`, `asset_type_fields`, `asset_type_revisions` | Saved private templates, stable field IDs and immutable definition snapshots (format 4) |
| `memory_sources`, `memory_entities`, `memory_aliases` | Original episodes and named records |
| `memory_facts`, `memory_evidence`, `memory_audit`, `memory_note_revisions` | Statements, provenance and preserved history |
| `reconciliation_purchases`, `reconciliation_lines`, `reconciliation_observations` | Purchase identity, quantities and source observations |
| `reconciliation_decisions`, `reconciliation_bindings`, `reconciliation_candidates` | Review history and separate physical units |
| `asset_actions`, `asset_proposals`, `receipt_proposals`, `receipt_details` | Corrections, reviews and receipt-line claims |
| `asset_consolidations` | Explicit two-record identity choices and preserved reversals |
| `maintenance_tasks`, `maintenance_revisions` | Original record links, stated dates/timezones and preserved task history |
| `purchase_evidence` | Cross-source purchase claims and revisions |
| `chat_conversations`, `chat_turns` | Conversations and saved requests/results |
| `photos`, `photo_assets`, `documents` | Metadata, links and extracted document text; no binary files |
| `research_findings` | Web research sources saved to an asset: URL, title, page date, excerpts, research time, removal time (format 5) |

Rows retain stored IDs and references, source quotes, quantities, states, valid
dates and system-recorded timestamps. The owner discriminator `user_id` is omitted;
every query selects only the authenticated owner's rows. Integer minor-currency
amounts remain integers and unknowns remain JSON null. A line total is still a
line total; exporting does not divide it among units or sum repeated claims.
Stored JSON text fields such as `value_json` and `result_json` remain exact strings
so no type, numeric literal or historical representation is silently rewritten.
Check the envelope format before consuming the document. It is not a database
dump or a supported replay/import protocol.

Format 2 adds consolidation history to the 23 format-1 collections; existing row
fields keep their previous meanings. Format3 adds the two maintenance collections,
preserving calendar dates and explicit unknowns without inferring completion or
intervals. The UI accepts formats 1/2/3 for server compatibility. Active
consolidation membership is a derived index and is not a
separate collection; both member IDs, choice dates and reversals are retained in
`asset_consolidations`. Check the envelope version before processing a file.

## Implementation and verification

`RecordExport` owns one explicit PostgreSQL read transaction, frozen table/column
projections, stable row ordering and whole-file bounds. It never selects binary
columns or automatically includes new tables/columns. The HTTP download adapter
requires a current session, origin and CSRF token, accepts only `{}`, derives the
owner from that session and returns an attachment with no-store/nosniff headers.
The response is fully prepared before download headers are sent; errors have no
attachment. There is no server-side temporary export file or model export tool.

Synthetic tests cover account/credential isolation, correction history, distinct
units, six exact currencies and withdrawn claims, deleted-file metadata, concurrent
writes during a stable snapshot, row/UTF-8 byte limits, read-only queries, HTTP
authentication and UI download/error/unmount behavior. Real personal data and
external providers are not involved in release verification.
