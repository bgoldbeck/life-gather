# Private text memory chat: first usable increment

Current scan action: [request a bounded Gmail text-evidence scan](EMAIL_SCANS.md)
from an explicitly selected connected mailbox. Chat saves the queue result and
links to Scans for progress/cancellation. No AI request or inventory write occurs.

Current photo capture: [direct private Chat uploads](PHOTO_EVIDENCE.md) and explicit
saved-photo reading reuse the existing single-item review workflow. Uploading saves
the original without an AI call; reading it is a separate explicit action.

The original text-memory increment provides three explicit actions:

- **Save memory** preserves the exact original text as a private source. It does
  not infer verified facts, merge possessions, or create inventory items.
- **Keyword search** finds original evidence using 1–12 literal words (all words
  must match). It works without an AI connection.
- **Ask OpenAI** plans a short keyword search, then answers from matching evidence
  with source buttons. If there is no matching evidence, it says so. Source IDs
  must belong to the retrieved evidence before the answer is accepted.

Open a source button to inspect the original statement. Sources and messages are
rendered as text, not HTML. Statements are not independently verified facts.
The answer is model-generated: source-ID validation proves the citation is in
the supplied evidence, not that every sentence is semantically supported.

## Correcting a saved note

Open a saved note's evidence and choose **Correct note**. Save the revised text
to create a new version. The original text remains available in **View note
history**, including from older conversation citations. **View current note**
opens the latest correction. New keyword recall and AI evidence use the current
version; previous conversation answers remain historical records.

Corrections apply only to explicitly saved text notes, require no AI connection,
and do not rewrite inventory, extracted graph facts, or their original evidence.
History timestamps show when versions were recorded, not when a real-world fact
became true. To revert a note, save its earlier text as a new correction.

Migration `0007_note_corrections` adds owner-constrained revision links without
changing existing sources. Saving the new source, its search index, revision link,
and audit entries is one transaction. Only the current version can be corrected;
stale edits conflict. A lost response can be retried with the same request ID,
returning the same version even after later corrections. History pages contain up
to 25 versions. Operator snapshots preserve revision links; the Python export
service includes the `note_revisions` collection alongside all original sources.

## OpenAI setup

1. The installation owner configures the optional vault key using
   [private settings](PRIVATE_SETTINGS.md).
2. Each user adds an AI credential in Settings with provider `openai`, their own
   API key, and a recognizable label. Credential storage does not itself send
   records to OpenAI or verify API access.
3. Enable external AI access in Settings. In Chat, choose Ask OpenAI, select that
   credential, and enter a Responses-compatible model ID available to the API
   account. No model is silently selected and no shared installation key is used.
4. Ask a question about saved evidence. The question, up to four recent user
   messages (1,000 characters each), and up to eight evidence excerpts (2,000
   characters each) can be sent to OpenAI. Save and keyword search remain local.

The adapter uses the fixed `https://api.openai.com/v1/responses` endpoint, verified
TLS, no redirects, no environment proxy inheritance, `store: false`, and structured
JSON output. It does not use provider-side conversations or previous-response IDs.
`store: false` is not a promise of zero provider retention; OpenAI account/data
policies still apply. See [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

No tools, write authority, credentials, SQL, shell, or filesystem operations are
given to the model. A typed `memory_save_text` MCP operation and chat capture use
the same deterministic service. The nineteen-tool app-session MCP endpoint has
fifteen read operations, two explicit note writes, and two human asset-review/
correction writes. External-client
OAuth remains unimplemented; never share application session cookies.

## Persistence, limits, and cancellation

Migration `0006_text_chat` adds conversations, turns, and daily usage with owner
constraints. Existing users and memory records are preserved. Conversations are
listed in UUID order with pages of 25; messages are ordered chronologically with
pages of 25. Conversations and failures survive reload/restart. Original sources
remain in the existing memory tables. Operator database snapshots include chat;
the restore test verifies it. A user-facing chat export/erasure flow remains ahead.

Each submitted turn has a stable request ID. Replays return its persisted state;
different content under that ID conflicts. Only one turn per user can run at a
time; the process admits four chat executions. Stale pending messages display as
interrupted after two minutes and do not resume automatically. A lost response can
be retried with the same ID without saving or calling the model again. A terminal
failed request needs a new submission to attempt new work.

The fixed limit is 20 AI questions per user per UTC day, reserved transactionally
before the provider call. Each question makes at most two provider requests, each
with at most 1,500 output tokens and a 40,000-byte serialized input limit. Reported
token usage persists. Reservations are retained on failure/cancellation because a
provider may have charged for incomplete work; token counts may be incomplete in
those cases. These limits are not a dollar-denominated spending guarantee.

Provider calls have a 25-second network timeout, a 128-KiB response cap, no automatic
retries, and a 65-second overall execution timeout. Chat request bodies are limited
to 32 KiB with a ten-second read timeout; text inputs are limited to 4,000 characters.
Session and consent are checked before each outbound request; sessions are also
checked during execution. Cancellation marks a pending turn, cancels the local
provider request, and prevents subsequent calls. It cannot retract content already
sent, guarantee the provider stopped computing, or undo an already committed save.
Leaving Chat aborts the browser wait; use Stop to request server cancellation.

## Verification and remaining scope

Tests use synthetic notes and mock provider responses. No real OpenAI API key or
live provider call is required for the suite. Tests cover two-user isolation,
CSRF, request/body limits, persistence/restart, concurrent replay, paging, invalid
citations, consent, durable reservations, cancellation, provider redaction, and
snapshot restore. Frontend tests cover capture, recall configuration, evidence
rendering, conversation reload, and retry identity.

Saved notes can now produce [reviewed asset proposals](ASSET_PROPOSALS.md). This is
an initial text slice, not the whole chat milestone. Broader structured extraction,
graph-fact correction/approval, the general discovery review queue, streaming
tokens, persistent provider/model preferences, and per-user Light/Dark settings
are still required in subsequent increments. Uploads and connectors remain later.
Real OpenAI access and model compatibility have not been smoke-tested. Completed,
tested feature increments follow the standing release rule in `AGENTS.md`.


## Reviewed receipt recall (v0.25.0)

Ask about a named asset's receipt total or purchase date. The existing bounded
recall plan finds up to two records and reads at most three currently linked
purchased receipt lines per asset. It uses the same owner-scoped `AssetPurchases`
contract as the Assets panel; no model write access or additional provider call.
Current reconciliation reassignment/dismissal/undo controls these links.

The answer context includes exact currency/amount strings and integer minor units,
line quantity, physical-unit position, latest detail revision, exact quotes and
source IDs. A shared receipt-line key identifies repeat appearances on multiple
physical units. The answer instructions forbid treating a full-line total as a
unit price, summing those repeated appearances, combining separate receipts or
currencies, and restoring withdrawn details from older raw source text.

Missing optional values remain unknown. Corrected/deleted sources are historical,
not current verified claims. Receipt-source markers also cover keyword-only recall
or context-budget omissions: if reviewed purchase entries are absent, instructions
require an unknown/limited answer rather than substitution from raw receipt text.
Literal amounts, dates and quotes are omitted as complete entries when the byte
budget is reached; the existing limit notice and read trace expose omitted context.

Original photo/PDF source labels and deletion metadata now survive named-record
recall even when keyword search misses that source. Cited source inspection uses
the existing evidence panel and receipt-review link. No database migration or new
dependency. All provider tests use synthetic responses; live answer quality and
instruction following have not been independently verified.


Named asset recall includes canonical inferred inventory membership and up to
three recent own or incoming correction records, even when their explanations
do not match the question's search text. This is bounded history, not ownership
verification. Original source metadata identifies superseded ownership and
replacement statement versions, preserves their known dates and reports how
many recorded association versions remain current after later moves. Source
inspection shows historical-state labels. Current purchase bindings remain the
basis for receipt claims; original episodes are never silently reassigned.
Incoming keyword history matches either linked item, scoped to the authenticated
owner and latest operation for each origin/target pair. Existing two-record,
eight-source and 24 KiB context limits, omission flags, two provider calls and
citation validation remain. Live model instruction following is not verified by
the deterministic synthetic-provider tests.


Citation inspection respects the active conversation and explicit evidence-close
intent. Late source pages/errors are ignored after navigation, closing or unmount;
a previous read cannot replace or stop the loading indicator for a newer one.
Receipt and asset review panels close when selecting/starting another conversation.
Draft text, completed turns and underlying reviewed records are preserved.
