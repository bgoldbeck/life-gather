# AI-driven asset assistant

Date: 2026-10-21. Status: first slice implemented in v0.60.0, asset types and
typed template fields in v0.63.0 (see
[AI assistant](../../AI_ASSISTANT.md) and its limits); remaining items below are open. This is an architectural extension of the existing chat runtime.

Priority alignment, 2026-10-21: [tracking-first feature plan](../../FEATURE_PLAN.md)
places this slice first, before new proactive automation, with later reliability
and UI beautification gates. The user approved that product direction and asked
to commit the revised roadmap; this draft is not a claim of implemented behavior.

## Intent and baseline

The user clarified that LifeGather should be mostly AI powered: natural language
and evidence interpretation belong to the configured AI, with application tools
performing reliable domain operations. The user agreed to prioritize an assistant
that chooses existing tools for natural-language asset creation and updates, asks
for missing details, and retains evidence. Another isolated extraction feature
does not address that experience gap.

Fetched GitHub main: `41cd377` (v0.59.0, migration `0026_asset_types`). The checkout
was clean, with no open PRs or remote feature branches. Historical detached
worktrees and archive branches remain untouched. Graphify relationship findings
were checked against current chat, organizer, recall and asset service source.

Current behavior:

- `chat/organizer.py` uses regular expressions for explicit navigation and profile
  commands. Only the VIN flow currently accepts a bare follow-up value.
- `chat/runner.py` uses configured OpenAI, Claude and Gemini adapters for bounded
  structured responses, extraction and read-only sourced answers.
- `chat/routes.py` sends `organize` to the deterministic organizer separately from
  provider execution. Streaming supports `ask` drafts and, since v0.61.0, host-written `assistant` progress status.
- Manual asset entry, custom asset types, profile corrections, identity review,
  account isolation and evidence/history services already exist. Their authority
  and validation remain in the application.

## Approach

Use a provider-neutral tool runner within LifeGather. The model selects typed
operations; the server executes an allowlist against the same domain services
that authenticated MCP exposes. Reuse the existing structured-completion adapter
contract initially: each completion selects a tool or returns a final answer or
clarification, then receives bounded tool results on the next step. This is model
tool selection, not translation of model text into fixed command strings.

Alternatives considered:

- Expanding the command parser would be smaller but retains the wording problem
  and does not meet the user's intent.
- Running an external coding agent/desktop automation inside the app introduces
  a separate runtime and permissions surface. It is unnecessary for this slice.
  Existing authenticated external MCP clients continue to work independently.

The feature uses configured model API connections. It does not imply that a
Codex or Claude desktop subscription supplies API credentials or that this
development chat becomes the application's runtime.

## First release behavior

R1. A configured AI assistant accepts ordinary asset requests such as "I own a
Makita drill, model DHP484; add it" and "The tire size on my F150 is 205/55R16."
It finds records, reads types/current fields, asks questions and performs supported
changes without requiring a special command phrase.

R2. Clear explicit create/update requests can execute without an extra approval
click. Merely asking a question, discussing an item, quoting a document or reading
an old conversation does not authorize a write. The model must select a write
operation tied to the active user request. Evidence validation, account checks,
identity rules and current-version checks remain server enforced. Semantic intent
classification remains fallible and must not be described as guaranteed.

R3. The slice supports one coherent operation on one physical asset per turn:
create it with its supplied details, or add/correct multiple supplied descriptive
fields together. Do not require a separate turn per field. Read operations and
clarification may precede the change. Validate every included field and commit
the complete operation atomically; an invalid or ambiguous field must not leave
a silently partial update. Keep existing bounded field/value limits. Multiple
physical assets require a separately scoped batch workflow. No operation after
a committed asset action can initiate another asset action in the same turn.

R4. Asset creation requires explicitly stated current ownership, a supplied name,
and the existing manufacturer context for model/serial. It may select a current
existing type when supported by the user's request; ambiguous types need a
choice. It does not create/edit type definitions or fill unsupported values.

R5. A selected physical record remains pinned to its server-resolved ID/version.
Without a selected record, the model can search the owner's inventory. Multiple
plausible records require a user choice. A duplicate candidate never authorizes
merging or a same-item decision by name alone; reuse existing reliable identity
rules and ask the user where human identity decisions are needed.

R6. Field changes support existing profile fields and current optional text type
fields. Supplied values must occur exactly in cited user evidence. Missing values,
multiple conflicting current statements, unsupported operations and stale versions
produce clarification or actionable refusal. No invented dates, ownership,
identifiers, prices, units or compatibility claims. Preserve original subjects
through supported consolidation/correction behavior.

R7. Follow-ups can resolve the specific saved clarification in the same
conversation. Persist typed pending intent, cited originating turn IDs, selected
identity and expected versions. "205/55R16" can answer a tire-size question;
"never mind" abandons it. Context/identity changes invalidate stale intent.
Earlier assistant prose and retrieved evidence cannot become authorization.
Only complete owner-scoped user turns may supply follow-up evidence; reject
incomplete/truncated histories instead of guessing what the user meant.

R8. Replies show the operation's actual outcome, an Open asset action, and source/
history links. Successful writes use a server-generated receipt; a final model
response cannot invent saved IDs or turn a failed write into success. A model
failure after a committed write must still show the committed receipt.

## Execution, privacy and data integrity

- Initial tool allowlist: bounded asset search, asset/type/current-field inspection,
  asset-creation preview, create asset with supplied details, and save a bounded
  collection of sourced descriptive fields atomically on one asset.
  A clarification/final-answer decision is part of the response schema.
- Account, request IDs, allowed source IDs, version tokens and permissions are
  host-owned. The model cannot choose an account, arbitrary database query, URL,
  credential, executable code or unrestricted MCP tool name.
- Use at most six model completions, eight read-tool calls and one atomic asset
  action per user turn, within the existing request deadline. One action may
  include multiple transaction-scoped field writes. Bound provider context to 24 KiB
  and return explicit limit/truncation states. No silent retries or open loops.
- Preserve existing provider selection, external-data consent, semaphore, daily
  turn budget and usage totals; account for every actual completion. Recheck
  permission, credential and cancellation before calls and before commit.
- Source documents, record names, tool results and previous model messages are
  untrusted data. They never grant tool authority or permissions.
- Save original user wording and originating follow-up evidence, inferred action,
  provider/model and actual operation outcome. Do not save generated manual-entry
  labels as if the user literally supplied those labels or ownership statements.
- Commit the domain write, evidence, durable operation receipt and completed turn
  atomically. Refactor existing services to expose transaction-scoped internals
  where necessary; HTTP and MCP retain their current public behavior.
- Recheck pending turn state under the write transaction. Cancellation or reviewed
  conversation deletion that wins before commit prevents the write; a completed
  operation remains visible when cancellation arrives after commit.
- Identical request replay returns the stored outcome without another model call
  or domain write. Changed inputs with the same request ID remain conflicts.
- Keep the structured action/result and pending clarification in bounded existing
  turn result JSON if possible. If schema changes become necessary, add a new
  migration after checking current main; never edit an applied migration.

## User interface and compatibility

Make the ordinary Assistant action use the AI runner when a configured connection,
model and explicit external-data permission are available. Show the selected
provider/model and explain setup when missing. Preserve existing local commands
as a clearly identified offline option; never silently send a local command to
a provider. Existing Ask AI saved turns retain their read-only meaning. Keep
save/search/extraction/scan modes and existing MCP contracts compatible.

The new assistant supports both sourced questions and the scoped actions; users
should not have to guess whether their sentence needs a separate AI mode.
Intermediate UI states may show checking records or saving, without exposing
private chain-of-thought. A draft/streamed answer cannot claim a write succeeded
before its durable receipt. Preserve drafts, context guards, accessible choice
controls, narrow layouts and Light/Dark themes.

## Acceptance and verification

A1. Scripted provider fixtures for all three adapters demonstrate different
natural phrasings selecting real tools, creating an explicitly owned asset with
supplied details and updating several supported fields in one request with exact
original user evidence and history. A single invalid field rolls back the entire
operation; valid fields do not silently commit on their own.

A2. Fixtures demonstrate missing ownership/manufacturer/value, two same-name
physical assets, current-field conflict, stale type/record, consolidated-member
correction and a generic follow-up resolved only to the intended pending request.

A3. Unknown tools/IDs, cross-owner access, embedded document instructions, invented
values, question-only writes, excess calls, unsupported multi-asset plans and
truncated context do not produce unauthorized or partially applied changes.

A4. Integration tests cover duplicate preview through write, atomic rollback,
lost-response replay with no extra provider call, cancellation/deletion races,
permission revocation and model failure after commit. Exercise the same domain
contracts through HTTP and existing MCP consumers without weakening their checks.

A5. Frontend interaction tests and synthetic desktop/390px browser verification
cover configured/unconfigured AI, clarification/identity choices, source links,
errors, drafts, context changes and trustworthy saved-operation receipts.

A6. Run backend pytest, strict mypy, Ruff, format and package build from backend;
frontend tests/types/lint/format/build from frontend; affected release/recovery
checks. Verify current and historical evidence plus two-user isolation through
export and recovery. Report synthetic versus live provider verification separately.

A7. After code verification, refresh Graphify and HTML once, update capability/
roadmap docs, CHANGELOG, README badge and the single version source for the next
available minor release (provisionally 0.60.0; recheck main first). Follow the
authorized commit/push/PR/merge and isolated linux/amd64 image smoke/publication
sequence. No running-installation redeployment or live personal-data ingestion.

## Scope boundary and next handoff

This feature does not add banking, web research, Gmail attachments, broad receipt
financial extraction, deletion/merge tools, arbitrary browser control, scheduled
agent activity or an unrestricted code-execution agent. Those remain separate
increments. The model chooses among implemented tools; domain checks can still
reject an unsafe or unsupported proposal and explain the next useful step.

Review this written design before preparing the implementation plan. Implementation
will run sequentially in the root chat, as required by the user's no-agent policy.
