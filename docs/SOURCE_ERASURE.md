# Source erasure

Since v0.99.0 you can erase one source and everything LifeGather made from it.
A source is a Gmail connection or one finished scan. Erasure is permanent: it
cannot be undone or restored in the app.

It sits between the two existing controls. [Deleting a memory](MEMORIES.md#deleting-memories-v0840)
removes the memory's text but keeps the assets, facts and purchases made from it.
[Deleting the account](ACCOUNT_DELETION.md) removes everything. Erasure removes
one source's rows and everything derived from them, and nothing else.

## Using it

- **Settings → Email connections → Erase everything from this mailbox.** Works
  for connected and disconnected mailboxes.
- **Scans → open a finished scan → Erase what this scan saved.** Erases the
  emails the scan read (including ones an earlier scan had already saved) and
  what was made from them. The Gmail connection and its schedules stay.

LifeGather first lists what will go, counted by kind (saved emails and memories,
assets, details, purchases, review suggestions, maintenance tasks, documents and
photos with their files, scans, schedules and the connection). Tick **I
understand this is permanent**, then **Erase permanently**. If anything changed
since the list was made, nothing is erased and the new list is shown to confirm
again. A source whose scan is still queued or running cannot be erased; cancel
the scan or wait for it to finish.

## What is erased

For a Gmail connection:

- every email memory its scans saved (text, import and attachment scans);
- documents its attachment scans created, with their stored files and reviewed
  text. A document you had already uploaded yourself, which the scan only
  linked to, stays;
- AI discovery results, scan runs and their results, scan schedules for it,
  its saved Google sign-in and the connection itself.

Then everything derived from those rows, found by following the database's
references, so new kinds of records are covered automatically:

- any record that points at an erased record: facts, evidence and its quotes,
  aliases, purchases and their evidence, receipt and asset suggestions,
  reconciliation decisions, photo links, maintenance, research findings and
  undo records of erased assets;
- a fact whose own evidence is all erased. A correction counts only the
  sources it added, not the evidence it carried over from the fact it replaced;
- search entries and history receipts for erased records.

One content-free `source_erased` receipt is written.

## What stays

- **Records a kept source also supports.** An asset or product model first
  created from an erased email stays when a source you keep has evidence about
  it (a note, a fact, an alias, maintenance, an asset action, or another
  email's purchase line). It is then attributed to the earliest such source.
  Its details from the erased source go; its other details stay.
- **Your corrections.** A kept correction of an erased fact keeps its own
  evidence and becomes the start of that history. A kept value that an erased
  correction had replaced becomes current again. Purchase evidence, maintenance
  and review decision histories are handled the same way.
- **Everything outside the source:** your notes, uploads, other mailboxes and
  other accounts.

Not changed: chat conversations that quoted an erased email (delete those in
Chat), the grant at Google (manage it in your Google account), and existing
exports, archives and backups.

## Integration

Both endpoints need the private session and CSRF token.

- `POST /api/erasure/preview` with `{"kind": "mailbox" | "scan", "id"}` returns
  `counts` and a `fingerprint` of exactly what would be erased.
- `POST /api/erasure/erase` with the same body plus `fingerprint` erases it and
  returns `counts`, `rows` and `files`. A changed source returns 409; another
  account's or unknown source 404; an active scan 409; a storage failure 503
  with nothing erased.

The service is `lifegather/erasure/service.py`. It reads the foreign keys from
`pg_catalog` like account deletion, runs as the account under row security,
holds the writer lock throughout and removes stored files before the rows in
the same transaction. No migration, no records-format change, and no MCP or
model erasure tool.
