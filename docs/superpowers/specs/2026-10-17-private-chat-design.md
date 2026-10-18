# Private chat with OpenAI and Claude

**Status, 2026-10-18:** Approved design for the broader chat runtime. The first
[text-memory chat increment](../../TEXT_CHAT.md) is now implemented on `main`:
local capture/search and optional OpenAI answers. This design remains a target
for further work, not a description of all currently shipped behavior. Reconcile
it with the existing chat schema and APIs before continuing implementation.

## Intent and approved scope

The user approved this scope on 2026-10-17: one shared conversation/tool runtime
with OpenAI and Claude adapters, private saved history, streamed replies, source
links, read-only memory tools, per-user usage limits, and explicit provider
selection. Chat will not modify inventory in this milestone.

LifeGather should open to a useful conversation workspace instead of its Chat
placeholder. A signed-in user can choose a configured provider, ask a question,
watch the answer arrive, inspect its evidence, and return to the same conversation
after a restart. Conversations belong to the user's stable workspace ID. A model
is not the source of truth for possessions or graph facts.

The user approved this written design and its implementation plan on 2026-10-17.
The broader runtime is not yet delivered; the current increment is linked above.

## Approach and alternatives

Use a shared Python orchestration service and two small provider adapters. Each
adapter converts the same typed history/tool/event contracts into its provider's
native API. Persistence, authorization, limits, evidence handling, and UI behavior
remain shared. Use official SDKs, verify their installed signatures before coding,
and lock the tested versions. Keep provider calls mockable.

A general agent framework could supply orchestration but would add session and
tool abstractions that overlap LifeGather's authority and persistence boundaries.
Two separate chat implementations would duplicate those controls and risk
different privacy/correction behavior. Neither is needed for this slice.

OpenAI uses the Responses API, explicitly disabling response application-state
storage with `store=false`; history is supplied from the local database. This
setting is not a promise of zero provider retention. Claude uses the Messages API
with locally supplied history. Both adapters support native function/tool calling
and text streaming. No provider-hosted web search, file store, code execution,
shell, remote MCP connector, or fallback provider is enabled.

## User flow and settings

Chat becomes the initial signed-in view. It has a bounded paginated conversation
list, New conversation, a provider/model selector, message history, a composer,
tool-activity feedback, Stop, and retry controls. Retain the approved calm sage
visual direction, accessible labels, keyboard behavior, and narrow-screen layout.
Do not show demonstration records as the user's data.

A new conversation binds to OpenAI or Claude, an allowed model, and one of the
owner's matching AI credentials. The provider cannot change within a conversation
in this slice; creating another conversation makes the destination explicit and
prevents accidental transmission of history to a different provider. No silent
fallback, provider comparison, or dual-provider broadcast.

Settings explain the destination and require the existing external-AI permission.
Use the existing encrypted owner-scoped vault; never expose a saved secret back
to the browser or accept credentials in chat messages. No installation-wide model
key is shared between users. Missing vault configuration, permission, credential,
or allowed model produces a useful setup state without making a provider request.
Verify supported model IDs during implementation; do not use a mutable latest
alias or claim a model is free. API usage is billed by the selected provider under
the user's account; existing chat subscriptions are not assumed to supply API
access. No live billed request is part of offline acceptance testing.

Provide Light and Dark choices in Settings with a per-user preference and sensible
initial system appearance. Apply semantic surface/text/border/focus/status tokens
across the shell, settings, chat, and evidence panel. Preference loading must not
reuse the previous signed-in user's choice. This satisfies the existing early-UI
appearance requirement rather than deferring it to dashboards.

## Storage and migration

Add an Alembic migration with owner-constrained conversation, message, run, usage,
and citation records, and a theme preference on the existing settings record.
Keep existing accounts, sources, and graph facts unchanged. Use composite owner
foreign keys for all chat relationships; matching UUIDs alone never confer access.

Conversations retain provider/model/credential reference, title derived locally
from the first message, creation/update time, and a stable ID. Messages retain
role, bounded text, ordering, run reference, and completion state. Persist user
messages before dispatch, completed answers atomically, and explicitly marked
partial answers on cancellation or failure. Do not label partial text as a
completed answer. Tool activity records retain safe operation names, cited IDs,
and dispositions, not duplicated full source bodies or credentials.

Runs record an owner-scoped idempotency key, status, selected provider/model,
dispatch count, tool count, timestamps, safe error classification, and usage.
Retries of the same submission do not insert another user message or dispatch a
second run. An explicit retry is a new run linked to the same user message; failed
and partial attempts remain distinguishable. Do not silently repeat a request
after ambiguous transport failure.

On restart, expired running leases become interrupted and remain inspectable;
there is no automatic provider resumption or billing. A single active run per
user is enforced transactionally, including concurrent workers. Provider/network
waits never hold SQLite write transactions. Chat participates in the existing
whole-database snapshot/restore path; test restoration of history and citations.

Chat text is private conversation history, not a newly asserted graph fact or
source episode. No asset creation, ownership confirmation, reconciliation change,
or implicit extraction occurs when a user sends a message in this release.

## Transport and execution

HTTP is the thin authenticated chat transport. Mutations and the POST streaming
endpoint require exact Origin and existing session CSRF. GET history and evidence
routes authorize the session and owner independently. Apply no-store and
no-referrer headers, body caps, bounded query/page sizes, and generic errors that
do not echo SQL, arguments, provider payloads, or secrets.

Use a POST fetch stream of typed SSE events for run start, tool activity, text
delta, usage, completion, cancellation, and safe failure. Persisted run state is
authoritative after refresh; a dropped browser stream does not start a replacement
provider call. Explicit Stop and disconnect cancel further execution at a safe
boundary; already received text is saved as partial. Do not claim that cancellation
can undo billing for an already dispatched request.

The shared runtime talks to the existing private MCP adapter using the official
MCP client over an in-process ASGI transport. Supply only the initiating session's
ephemeral cookie/CSRF and configured installation Host/Origin; never persist those
secrets or send them to a model. Reuse the running host SDK lifespan. This exercises
the actual authenticated protocol instead of bypassing it through unrestricted
in-process tool calls. No arbitrary MCP URL is accepted from the user or model.

Only the existing ten read-only tools are available. The runtime validates each
call, routes it through MCP, and returns a bounded result to the selected model.
The model sees no user/owner/context argument. Authorization remains enforced by
MCP and domain services even if the model fabricates IDs or follows source text.
Recheck the initiating session, external-AI permission, run cancellation, and
credential ownership before every provider dispatch and tool execution.

## Evidence and model context

Instructions distinguish stated, verified, inferred, and unknown facts. Source
content is untrusted evidence, never an instruction to expand tools, change
provider, expose credentials, or access another workspace. Preserve complete
tool-call/result groups in bounded context. When local history exceeds the
context bound, exclude older complete turns with a visible context-limit notice;
do not silently invent a summary or discard part of a tool exchange.

Answers may cite source IDs obtained from successful owned tool results. Build a
server-side citation registry and validate references against it and current
ownership. Model-invented or foreign IDs never become clickable citations. A
source panel fetches original text through a thin authorized adapter using the
same source paging limits as MCP. Render messages/source text safely; no raw HTML,
remote image loads, or active links supplied by untrusted source text.

Show inference and unknown status in evidence views. A receipt mention or a
historical fact does not become a claim of confirmed present ownership. When no
evidence is available, the assistant must say so; the UI must not manufacture
citations or a successful save indicator.

## Resource and usage controls

Initial application bounds, configurable downward by the installation owner:

- One active run per user and four active runs per process.
- 8,000 characters per submitted message, 50 messages per history page, and a
  64-KiB aggregate serialized context budget including instructions/tools/results.
- At most four provider dispatches and eight sequential tool calls per run.
  No parallel tool calls or unbounded loops.
- At most 2,048 output tokens per dispatch and a 120-second run deadline.
  Existing MCP payload, traversal, source-page, and rate limits still apply.
- A configurable per-user daily dispatch allowance, default 100, reserved
  atomically before each outbound request using a UTC accounting day. Count an
  ambiguous dispatched failure against that allowance; do not restore capacity
  merely because no answer arrived. Show the accounting timezone and reset time.

Record provider-reported token usage per dispatch and aggregate per user, retaining
input/output/cache categories separately. Interrupted usage may be unknown; label
it rather than recording zero. Request allowances and output caps bound execution
but are not a guaranteed dollar budget. No fabricated cost estimate, automatic
retry, or unlimited background run. Provider-side spending controls remain useful
and must not be represented as application-enforced monetary limits.

## Acceptance and boundaries

Use mocked streaming providers to test both protocol adapters and the shared
runtime without network credentials or personal data. Verify persistence/restart,
snapshot restore, concurrent per-user run claims, submission retries, daily quota
reservation, bounded tool loops/context, partial streams, cancellation, unknown
usage, permission revocation, removed credentials, and safe provider failures.

Exercise the real private MCP client path with two users. A guessed conversation,
run, message, source, citation, or credential ID must not reveal another user's
data. Embedded source instructions must not gain write tools or redirect an API
request. Mocked upstream tests verify the selected owner credential is used and
cookie/CSRF/source text never appears in credential headers or logs.

UI tests cover setup, both provider choices, saved conversations, stream/stop/error
states, accessible citations/source paging, reload, and theme isolation. Run
backend/frontend tests, lint/format/types, build and migration/package checks;
refresh the local source graph and commit the passing feature locally.

Stop at private read-only chat. Writable memory tools, uploads/extraction, email
scans, scheduling, web research, external-client OAuth, subscription-based provider
login, and live bank connections remain later work. This design does not authorize
paid API calls, pushes/merges of the future chat implementation, or another Docker
rebuild/upload. The current approved Docker publication covers the already merged
authentication, reconciliation, and MCP source only.

## Primary API references

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI Responses migration and local state](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
- [Claude tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)

Checked as design references on 2026-10-17. Verify concrete SDK signatures, model
availability, and API request/usage fields again when implementing the adapters.
