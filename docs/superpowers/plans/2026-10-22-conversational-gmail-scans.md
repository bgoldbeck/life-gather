# Conversational Gmail scans: implementation plan

Feature plan Phase 2, item 3: "Start existing Gmail purchase-discovery scans
conversationally with explicit mailbox/time/purpose scope." Baseline: main at
v0.60.0 (`b67bf13`), migration head `0026_asset_types`. Parallel work: asset type
assignment in the assistant (`claude/ai-assistant-asset-types`) also edits
`chat/assistant.py`; scan logic lives in a separate module to keep overlap small.

## Scope

Extend the v0.60.0 AI assistant tool runner with two tools over the existing
private scan queue. No new scan handler, worker, schedule or schema change.

- `list_mailboxes`: the owner's connected Gmail mailboxes (ID and address). Counts
  as a bounded read.
- `start_email_scan`: enqueue one existing `gmail_discovery` (purchase discovery
  with the assistant's own AI connection/model) or `gmail_import` (evidence only,
  no AI) run for one mailbox and an inclusive UTC date window.

Host checks before enqueueing (all refusals save nothing):

- The user's words must state the purpose and the time period: `purpose_quote`
  and `period_quote` must appear in the request or the pending question's origin.
  The model resolves the period to dates; the receipt shows the exact window.
- With several connected mailboxes, the chosen address must appear in the user's
  words; otherwise the assistant asks. Mailbox IDs must come from `list_mailboxes`.
- Dates are past, at most 31 days, ending no later than today; a message limit
  other than the default 20 must appear in the user's words (max 50).
- Existing handler checks still apply: mailbox revision, vault, external-AI
  permission, AI connection, one active run per mailbox and 20 runs per day.
- The scan enqueue and turn completion commit together; a stopped request never
  queues a scan. Replays return the stored receipt without a model call or a
  second run.

The receipt is server-generated with the run's real scope and a **View email
scan** link (existing Chat rendering of `scan_run_id`).

## Acceptance checks

1. "Find purchases in my Gmail from March 1 to March 15" queues one discovery run
   with the assistant's connection/model and the exact window; replay is a no-op.
2. Evidence-only wording queues a `gmail_import` run without AI configuration.
3. Missing purpose/period quotes, future or over-long windows, invented message
   limits, unknown or foreign mailbox IDs, and an unnamed choice between two
   mailboxes queue nothing.
4. A busy mailbox, disabled external AI and a request stopped before commit queue
   nothing and report why.
5. A clarification about the mailbox or period resolves on the next message.
6. Strict schema test covers the new nested object for all provider adapters.

Docs: AI_ASSISTANT.md, FEATURE_PLAN.md, CHANGELOG, next minor version.
