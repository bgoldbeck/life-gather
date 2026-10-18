# Private Chat Implementation Plan

**Status, 2026-10-18:** Approved plan for the broader runtime, not a completed
implementation report. The separate [text-memory chat increment](../../TEXT_CHAT.md)
is implemented on `main`. Reconcile this plan with that increment's schema,
migrations and APIs before executing remaining tasks; do not create conflicting
migration revisions or replace existing user history.

> **For agentic workers:** Use `superpowers:executing-plans` in the main/root
> chat. The user forbids subagents, delegation, and parallel agent work. Implement
> tasks sequentially and self-review each passing task.

**Goal:** Give each signed-in user persistent, sourced, read-only chat with an
explicit choice of OpenAI or Claude.

**Architecture:** Framework-independent services own chat persistence, run claims,
quotas, and orchestration. Two replaceable native provider adapters stream typed
events; one authenticated in-process MCP client exposes the existing read-only
tools. HTTP and React are thin authenticated transport/presentation layers.

**Tech Stack:** Existing Python 3.13/FastAPI/SQLAlchemy/Alembic/SQLite, official MCP
v2 client, official OpenAI/Anthropic Python SDKs verified and locked at execution,
React/TypeScript, existing shadcn primitives and semantic theme variables.

**Spec:** [Approved private chat design](../specs/2026-10-17-private-chat-design.md).
The user approved the written design and this plan on 2026-10-17.
Main/root execution is already selected by user policy.

## Global constraints

- User data, history, runs, credentials, citations, and limits remain owner-scoped.
- No automatic provider switch; no writes to memory or inventory from chat.
- External-AI permission defaults off and is checked before outbound requests.
- Never persist or send app session/CSRF secrets to a model. No raw provider errors
  or secret-bearing payloads in responses/logs.
- Limits: one active run/user, four/process, message 8,000 characters, history page
  maximum 50, total serialized model context 64 KiB, four dispatches/eight
  sequential tools/run, 2,048 output tokens/dispatch, run deadline 120 seconds.
- Daily dispatch allowance defaults to 100/user/UTC day, reserved atomically.
  Interrupted token usage is unknown, not zero; no guaranteed dollar budget.
- Original source paging and all MCP transport/output limits remain enforced.
- Light/Dark preference is private and persistent; initial default is System.
- Mock providers and synthetic data only during verification. No live billed
  request, source push/merge, or Docker operation without separate authorization.
- Preserve the unrelated edits in `docs/AUTH_REQUIREMENTS.md` and
  `docs/FIRST_TASK.md`; commit only intended passing changes.

## Review focus

1. Reusing a submission key with different text must reject, not replay the wrong
   message or charge twice (Task 1).
2. Permission/session/credential removal after streaming begins must stop the next
   tool or provider dispatch without revealing secrets (Tasks 3–4).
3. Malformed or interrupted tool-argument streams must never execute partial
   JSON, retry a billed request, or report unknown token usage as zero (Tasks 2–4).
4. Refresh/Stop/disconnect and server restart must preserve partial answers and
   avoid starting duplicate or automatically resumed runs (Tasks 1, 4–6).
5. Switching signed-in users must clear history, evidence, streams, and theme
   state before showing the next workspace (Task 6).

## Files and interfaces

Create `backend/src/lifegather/chat/` with `models.py`, `schemas.py`, `store.py`,
`contracts.py`, `providers.py`, `mcp_client.py`, `runtime.py`, and `routes.py`.
Each module owns the responsibility named by its file; do not put service logic
in routes. Add migration `0006_private_chat.py` after `0005_email_auth.py`.

Modify migration metadata imports, `config.py`, `main.py`, credential preference
models/service/routes, and the existing request-body limiter where required.
Create `frontend/src/chat/{ChatPanel,ConversationList,MessageList,Composer,
EvidencePanel}.tsx`, `chat/api.ts`, `chat/types.ts`, and `ThemeSettings.tsx`.
Modify `App.tsx`, `index.css`, and existing settings integration. Keep components
small; use existing UI primitives and avoid another state-management framework.

### Task 1: Durable private conversations, run claims, usage, and appearance

**Files:** chat models/schemas/store; migration 0006; migration metadata imports;
credentials models/service; tests `test_chat_store.py`, `test_chat_migration.py`.

**Interfaces:** `ChatStore(engine: Engine, clock: Callable[[], int])` provides
`create(actor: Account, data: ConversationInput) -> ConversationView`,
`conversations(actor, cursor: str = '', limit: int = 25) -> ConversationPage`,
`messages(actor, conversation_id: str, cursor: int = 0, limit: int = 25) -> MessagePage`,
`submit(actor, conversation_id: str, data: Submission) -> RunView`,
`claim_dispatch(actor, run_id: str, daily_limit: int) -> DispatchView`,
`finish_dispatch(actor, dispatch_id: str, usage: TokenUsage | None) -> None`,
`finish_run(actor, run_id: str, data: RunCompletion) -> RunView`,
`cancel(actor, run_id: str) -> None`, `recover_expired() -> int`, and
`run(actor, run_id: str) -> RunView`. All input/output classes live in schemas;
invalid/foreign IDs use the same `ChatError(message, status)`.

- [ ] Write failing tests for two-owner create/list/messages/run isolation,
  8,001-character rejection, page 51 rejection, and composite-owner foreign keys.
  Add a `chat_fixture` fixture supplying a migrated temporary AuthStore, two
  synthetic Accounts, and an injectable microsecond clock.
- [ ] Add tests that submit the same key concurrently: one user message, one run,
  one active claim; a changed message with that key returns conflict. A distinct
  retry key may retry an existing failed message without inserting it again.
- [ ] Run `uv run --locked pytest tests/test_chat_store.py -q` from `backend/`;
  expect missing-module/behavior failure before implementation.
- [ ] Implement owner-constrained `chat_conversations`, `chat_messages`,
  `chat_runs`, `chat_dispatches`, and `chat_citations`. Give messages monotonic
  per-conversation sequence numbers. Unique owner/submission keys prevent replay;
  a unique partial index on running user IDs enforces one active run across workers.
  Store credential UUID as an owner-validated logical reference: deleting a vault
  credential must preserve history and make future dispatch fail setup checks.
- [ ] Implement transactionally serialized claims/quota reservations with
  `BEGIN IMMEDIATE`; never hold a transaction over network waits. Persist run
  lease expiry and safe status transitions. Unsettled dispatched usage remains
  null/unknown; reserved daily dispatches still count after ambiguous failure.
- [ ] Add `theme` constrained to `system|light|dark` on UserSettings, preserving
  existing allow_external_ai values and backwards-compatible preference methods.
  New theme-specific read/write service methods must not overwrite AI permission.
- [ ] Test concurrent claim at allowance 1 permits exactly one dispatch, UTC reset
  boundaries, expiry/restart interruption, completed versus partial messages,
  cross-owner citations, and missing removed credentials. Test upgrade from 0005
  preserves existing accounts, preferences, memory, and reconciliation records.
- [ ] Run store/migration and existing private-settings tests, Ruff and mypy;
  inspect Alembic metadata consistency; commit the passing storage slice locally.

### Task 2: Typed streaming adapters for both providers

**Files:** chat contracts/providers; backend pyproject/lock; `test_chat_providers.py`.

**Interfaces:** `Provider = Literal['openai', 'anthropic']`;
`TokenUsage` retains input/output/cache categories, with absent usage nullable.
`ProviderEvent` is a discriminated union of TextDelta(text), ToolCall(id, name,
arguments), Usage(value), and ProviderDone(reason). `ProviderAdapter.stream(request:
ProviderRequest, secret: SecretStr) -> AsyncIterator[ProviderEvent]` consumes bounded
native-history items and MCP tool schemas. `ProviderRequest` includes provider,
model, messages, tools, and max_output_tokens; it cannot contain arbitrary URLs.

- [ ] Inspect current official SDK/version metadata and documented model IDs;
  install and lock `openai` and `anthropic`, then inspect actual async streaming,
  tool-result, timeout/retry, and usage signatures. Record verified versions and a
  small explicit model allowlist in the implementation docs; no latest aliases.
- [ ] Write failing mocked HTTP/stream tests for text, interleaved tool arguments,
  usage, malformed events, provider failures, premature EOF, and cancelled streams.
  Verify OpenAI sends `store=false`; neither request contains app cookies/CSRF.
- [ ] Run `uv run --locked pytest tests/test_chat_providers.py -q`; verify failure.
- [ ] Implement both adapters with SDK automatic retries disabled, fixed official
  endpoints, redirects disabled, and bounded request/response buffers. Pass
  Secrets only into authentication headers. Never log provider bodies/headers.
- [ ] Normalize only complete validated tool calls after their end event. Preserve
  required provider-native continuation items in run-local context, not model
  private reasoning in durable chat. Reject unavailable model/provider choices.
  Report missing usage as unknown and incomplete answers as partial.
- [ ] Verify mocked auth/bad-key/rate-limit/timeout errors produce safe typed
  failures and exactly one outbound attempt, with no raw error echo. Cap output
  at 2,048 tokens and reject malformed overlarge tool arguments before execution.
- [ ] Run provider tests, Ruff, format and mypy; commit passing adapters locally.

### Task 3: Authenticated MCP client and validated evidence registry

**Files:** chat mcp_client; `test_chat_mcp.py`; source adapter tests.

**Interfaces:** `ReadTools` has async `list() -> list[ToolDefinition]` and
`call(name: str, data: dict[str, JsonValue]) -> ToolResult`; its implementation
`AppMCPTools` uses the official client with an ASGI transport and an ephemeral
session grant. `ToolResult` contains safe structured data and owned source IDs.
No secret fields may appear in its repr/serialization. `CitationRegistry` accepts
only source IDs actually returned by owned successful reads, then resolves a
model reference to `CitationView | None` through MemoryService authorization.

- [ ] Write failing tests driving actual MCP discovery/read requests for two
  users, forged owner/context arguments, foreign IDs, revoked sessions, source
  instructions, and oversized results. Direct unguarded calls must still fail.
- [ ] Run `uv run --locked pytest tests/test_chat_mcp.py -q`; verify failure.
- [ ] Implement the official SDK client on the host's existing lifespan, with
  fixed in-process transport and correct protocol metadata. Supply only the
  initiating session Cookie/CSRF and configured Host/Origin; expose exactly the
  ten existing tools. Do not change MCP's authority contract or relax its limits.
- [ ] Recheck session, cancellation, external permission, and owner credentials
  before tool execution. Treat tool errors as bounded data, not new instructions.
  Collect source IDs using known result fields, not arbitrary strings in text.
- [ ] Test invented citation IDs, foreign IDs, removed evidence, source paging,
  inferred/unknown status, and prompt-like content. No raw HTML/remote loads or
  fabricated clickable sources may result; no graph audit writes occur.
- [ ] Run new and existing MCP tests, Ruff and mypy; commit locally.

### Task 4: Bounded shared run orchestration

**Files:** chat runtime; config; `test_chat_runtime.py`, `test_chat_recovery.py`.

**Interfaces:** `ChatRuntime(store, private_settings, providers, tools_factory,
limits)` exposes `execute(actor: Account, run_id: str, grant: SessionGrant) ->
AsyncIterator[ChatEvent]`. `ChatEvent` discriminates run_started, tool_started,
tool_finished, text_delta, usage, completed, cancelled, failed. It includes a run
ID and safe payload only. `SessionGrant` is ephemeral and never a domain record.

- [ ] Write failing fake-provider tests for both providers using the same saved
  conversation. Assert one active run/user, four/process, four model dispatches,
  eight sequential tools, 64-KiB context including schemas/results, 120-second
  deadline, and the atomic default 100-dispatch UTC quota.
- [ ] Run runtime tests and verify failure before implementation.
- [ ] Implement shared orchestration, an injectable process semaphore, monotonic
  deadline, cancellation checkpoints, and bounded native tool-result continuation.
  Use off-loop bounded calls for blocking database work. Keep credentials only for
  the current outbound call; recheck selection, permission and session each time.
- [ ] Build context from complete historical turns plus fixed instructions and
  selected-provider data only. Drop oldest complete turns when necessary and emit
  a visible context notice. Reject if even the current turn/tools cannot fit.
  Never summarize implicitly or forward prior partial responses as completed facts.
- [ ] Persist partial text on timeout, cancel, disconnect, malformed EOF, or lease
  loss; settle reported usage once or leave it unknown. Never auto-retry. An
  explicit retry uses a new run but the original user message. Recover interrupted
  runs at startup without dispatching. Bound/finalize leases and process slots in
  `finally` paths, including generator closure and provider cancellation.
- [ ] Test mid-stream permission/session revocation and removed/replaced keys;
  provider mismatch, tool loops, invented citations, quota racing, UTC rollover,
  ambiguous failure, restart, and snapshot/restore. Use fake clocks, not long sleeps.
- [ ] Run runtime/recovery/store/provider/MCP tests and quality checks; commit locally.

### Task 5: Thin authenticated chat transport and settings

**Files:** chat routes; main; config/body limiter; credentials routes;
`test_chat_http.py`, existing private settings tests.

**Interfaces:** `/api/chat/conversations` GET/POST; `/api/chat/conversations/{id}/messages`
GET; `/api/chat/conversations/{id}/submit` POST streaming; `/api/chat/runs/{id}` GET;
`/api/chat/runs/{id}/cancel` POST; `/api/chat/runs/{id}/retry` POST streaming;
`/api/chat/sources/{id}` GET with offset/limit; `/api/chat/capabilities` GET with
allowed models/provider setup/usage metadata only; `/api/appearance` GET/PUT.
Submission includes text and a UUID idempotency key; retry includes a new key.

- [ ] Write failing HTTP tests for two-owner resource guessing, CSRF/Origin,
  request limits, quota 429, stream termination, replay, and safe setup/error states.
  Assert appearance writes preserve external-AI permission and vice versa.
- [ ] Run `uv run --locked pytest tests/test_chat_http.py -q`; verify failure.
- [ ] Implement thin routes using existing authenticated/mutation dependencies.
  Cap chat request bodies at 48 KiB before JSON parsing (allows escaped 8,000-char
  text), enforce strict schemas, and use no-store/no-referrer. Stream typed SSE
  through POST fetch; do not use query-string secrets or EventSource tokens.
- [ ] Register services/providers with injectable fakes in create_app and recover
  leases inside lifespan. Authorize initial state before streaming; catch later
  failures as safe events. Disconnect/Stop closes the runtime and preserves partial
  history. GET state after refresh never submits or resumes work.
- [ ] Exercise both mocked provider destinations through the whole HTTP→runtime→
  official MCP client path. Check secret/error redaction and no graph writes.
- [ ] Run full backend tests, quality checks, package build/migration contents;
  commit the passing HTTP slice locally.

### Task 6: Private chat UI, evidence inspection, and themes

**Files:** frontend chat components/api/types; ThemeSettings; App; index.css;
tests `chat/ChatPanel.test.tsx`, `ThemeSettings.test.tsx`, existing UI tests.

**Interfaces:** ChatPanel takes csrfToken and refreshSession, renders typed server
capabilities/history/events, and clears all state on account change. Shared API
helpers send same-origin credentials and CSRF, support AbortSignal, and parse a
bounded incremental UTF-8 SSE stream without splitting multibyte characters.
ThemeSettings reads/writes `/api/appearance`; set `data-theme` only for the current
account, using prefers-color-scheme for System.

- [ ] Write failing interaction tests for both provider choices, setup permission,
  new/reopened conversations, streaming, Stop, partial/error/retry states, citation
  opening/paging, empty state, limit/reset display, and user-switch clearing.
  Add fragmented UTF-8/event parser fixtures and untrusted text rendering cases.
- [ ] Run `npm test -- --run` from frontend and verify new tests fail.
- [ ] Implement responsive components with existing buttons/cards/labels; Chat is
  the default signed-in view. Provider binding is explicit on new conversations,
  immutable afterward, and never auto-fallbacks. Model/credential choices come from
  capabilities, not free-form URLs or secrets. Disable duplicate submit while a
  run is active; refresh uses GET state. Keep unsent drafts only in memory.
- [ ] Implement source panel with server-validated citations and paged plain text.
  Render model/source strings without raw HTML, remote media, or auto-active links.
  Do not claim a memory/asset was saved or confirmed by this read-only release.
- [ ] Add semantic theme tokens for shell/forms/chat/evidence/focus/status, the
  private Light/Dark/System setting, system change handling, and safe user-switch
  reset. Preserve contrast and keyboard focus in both modes.
- [ ] Run UI tests, lint, typecheck, formatting and production build. Inspect both
  themes and narrow/wide layouts in the browser using synthetic data and fake
  providers. Run full backend tests for integration changes; commit locally.

### Task 7: Whole-feature verification and handoff

**Files:** README, PROJECT_PLAN, new `docs/PRIVATE_CHAT.md`, checked plan statuses.

- [ ] Review the final diff against every spec section and Review Focus item.
  Correct missing tests/behavior before marking tasks complete; use no agents.
- [ ] From backend, run `uv run --locked pytest`, Ruff check/format, mypy, and
  `uv build --wheel`. Verify migration 0006 and chat modules in the wheel, metadata
  parity, upgrade preservation, restart, and backup restoration with citations.
- [ ] From frontend, run tests/lint/typecheck/format/build. Run the nine offline
  publisher tests and both Compose config checks if deployment inputs changed.
  No actual Docker rebuild/upload is authorized by this plan.
- [ ] Document setup/destinations, API-billing distinction, real-call verification
  limits, per-user privacy, quota/reset and unknown usage, read-only behavior,
  cancellation, migrations/backups, and themes. Mark real provider smoke tests
  pending unless separately authorized and completed with explicit per-user consent.
- [ ] Refresh Graphify code-only using one worker/concurrency and no clustering;
  export HTML. Stage exact intended paths, commit the passing feature/docs, and
  report hashes, tests, migration consequences, and remaining limitations.
- [ ] Stop before writable tools/uploads/connectors. Do not push, PR, merge, or
  rebuild/upload this new chat feature without a new user instruction.
