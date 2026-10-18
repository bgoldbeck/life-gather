# Private text memory chat: first usable increment

Chat now provides three explicit actions:

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
the same deterministic service. The eleven-tool app-session MCP endpoint now has
ten read operations and this one explicit, idempotent source write. External-client
OAuth remains unimplemented; never share application session cookies.

## Persistence, limits, and cancellation

Migration `0006_text_chat` adds conversations, turns, and daily usage with owner
constraints. Existing users and memory records are preserved. Conversations are
listed in UUID order with pages of 25; messages are ordered chronologically with
pages of 25. Conversations and failures survive reload/restart. Original sources
remain in the existing memory tables. Operator SQLite snapshots include chat;
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

This is an initial usable text slice, not the whole chat milestone. Structured
extraction, graph-fact correction/approval, discovery resolution UI, streaming
tokens, persistent provider/model preferences, and per-user Light/Dark settings
are still required in subsequent increments. Uploads and connectors remain later.
Real OpenAI access and model compatibility have not been smoke-tested. Source
changes do not rebuild or publish an image; those operations remain separately
approved.
