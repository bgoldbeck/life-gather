# Your maintenance tasks

In **Profiles**, select the existing asset or place, then **Add maintenance task**.
Supply a title and original statement. Leave **Due date is known** unchecked when
you do not know a date; checking it requires an actual calendar date. Review the
IANA **Date timezone**, such as `America/Los_Angeles`, before saving.

These are your statements, not independently verified maintenance recommendations.
LifeGather does not infer intervals, ownership, parts compatibility, warranty
coverage or completion from a profile specification or an overdue task. Existing
freeform maintenance details remain separate and are not automatically converted.

## Dates, states and history

The **Maintenance** page lists tasks across your private records. Open tasks are
the default; filters also show completed, canceled or all tasks. Known due dates
sort first, then date and identifier; unknown dates sort last. **More maintenance
tasks** continues the bounded list. Due today, past due and upcoming use the task's
stated timezone, including local midnight and daylight-saving changes. A due date
is a calendar date, not an invented appointment time.

Use **Manage in Profiles** to open the correct linked record.
Profiles initially shows all task states, so a completed or canceled task remains
available when you follow its link from Maintenance. **Edit task** reads
its current version before opening a form. You can change the title/date/timezone,
mark completion, cancel a plan or reopen a mistaken completion/cancellation.
Every change requires a fresh source statement and keeps the earlier revision.
Completion dates can be explicitly unknown and are never filled with today's date.
Reopening/canceling clears completion from the new revision, while history retains
the old statement.

**Open current statement** and **History** expose the exact original statements,
earlier states/dates, recording times and workflow attribution. Due/completion
dates describe the task; recording time describes when the statement was saved.
No original source event date is inferred from a planned due date.

If another request changes a task or its consolidated identity, saving refuses the
stale version and preserves your unsaved draft. **Discard draft and reload task**
explicitly replaces it with the current version; the app never silently rebases
an old edit. Ordinary failed saves keep the draft and exact retry identity. A stale
list cursor requires refreshing the list.

The first increment creates no automatic reminders, repeating schedules, mileage
triggers, background jobs or external notifications. The built-in assistant does
not plan or mutate maintenance through a model tool. Direct entry works without
an AI provider.

## Identity and private storage

Each task retains the original asset/place identifier. Reads show its current
consolidated identity, while task sources/history keep the original link. Equal
task or item names do not combine records. Complete-record comparisons include
bounded current task statements; new task changes invalidate earlier consolidation
previews and block an unreviewed reversal. An unchanged consolidation can reverse
without rewriting task provenance. Existing empty comparison receipts keep their
previous token contract.

Migration `0024_maintenance` adds `maintenance_tasks` and `maintenance_revisions`,
with owner-constrained record/source/previous-revision references and one current
revision per task. Creates and changes save source, revision and audit atomically.
No schema or dependency outside this bounded domain is introduced. Operator
downgrades remove these new tables; make a tested backup before a downgrade.

[JSON records](RECORD_EXPORT.md) format 3 explicitly includes both collections,
calendar dates, unknowns and full history. [Personal ZIP archives](PERSONAL_ARCHIVE.md)
retain the same records payload and active originals. [Encrypted recovery](OPERATOR_RECOVERY.md)
preserves the whole installation; the current reader accepts migration 0023 and 0024
snapshots, validates current task storage and never activates a restored installation.
Transcript deletion retains these independently saved tasks and their sources.

## Adapters

HTTP reads use the private session; writes also require same-origin/CSRF checks.
`GET /api/maintenance` accepts optional `entity_id`, state, cursor and limit.
`GET /api/maintenance/{id}` returns current revision and state token;
`GET /api/maintenance/{id}/history` pages original revisions. `POST /api/maintenance`
creates a task and `POST /api/maintenance/revise` requires its fresh state token.
Closed bodies reject owner overrides and numeric/datetime date coercion. Responses
use `no-store`, and missing/foreign IDs or cross-filter cursors are refused.

The private MCP adapters are `maintenance_list`, `maintenance_get`,
`maintenance_history`, `maintenance_create` and `maintenance_revise`. Writes are
explicit, validated user operations with stable request IDs; no general SQL, shell,
credential, provider or filesystem tool is added. Exact retries acknowledge the
original revision even after later corrections and cannot rewind history.
