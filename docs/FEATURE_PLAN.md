# LifeGather feature plan: tracking first

User decisions: 2026-10-21. This is the active feature priority plan. It supersedes
the future-feature ordering in PROJECT_PLAN.md and the 2026-10-18 ordered roadmap;
those documents retain architectural constraints and historical delivery evidence.
The user wants reliable tracking before proactive automation, with a dedicated UI
beautification phase. This plan changes priorities, not implemented capabilities.

## Product goal

Make LifeGather a private, AI-first memory and tracking application: tell it about
something, give it evidence, find it later, and correct it without losing history.
Chat is the primary interface; lists, details, evidence and graph views make the
AI's work inspectable and editable. Direct access, correction and recovery must
remain useful when no AI provider is available.

AI interprets requests and sources and selects supported tools. Domain services
validate, authorize, reconcile and persist the result. Adding more fixed command
phrases is not the main strategy for conversational capability. AI-generated
claims are not automatically verified facts.

Existing requested/scheduled Gmail scans remain available. Tracking-first does
not disable delivered capabilities or prohibit AI from executing a clear user
request. It defers new proactive behaviors such as unsolicited reminders, renewal
monitoring and autonomous life-management actions.

## Current starting point

Source baseline checked against fetched main on 2026-10-21: v0.59.0,
`41cd377631a9996b1cda901a98d61071c7d06628`, migration `0026_asset_types`.
Private accounts, sourced records/history, inventory, asset types, file evidence,
receipt review, Gmail scans/schedules, manual maintenance, graph, three model
adapters, exports and operator recovery already exist. Broader conversational
writes are still proposed. See [capabilities and limits](CAPABILITIES_AND_REMAINING_WORK.md).
Source availability does not establish the running server's version or live
provider health.

## Phase 1: natural-language tracking through AI

Build the shared AI tool runner over existing private services. Start with asset
creation and supplied-field updates, then extend only when the existing operation
and its evidence/identity behavior are ready. Use the configured OpenAI, Claude or
Gemini connection; external authenticated MCP clients remain supported separately.

- Understand ordinary wording, find/read records and types, ask for necessary
  clarification, and perform clear supported requests without redundant approval.
- Support a coherent multi-field operation on one asset: "Add my mower with this
  manufacturer, model and serial" or "Update its paint and filter size." Do not
  require one turn per field. Validate the complete operation before committing;
  return all-or-nothing results rather than silently saving only some fields.
- Preserve unknowns, stated versus inferred information, original wording,
  provenance, current and historical facts, ownership and distinct physical units.
- Resolve ambiguous identity and conflicting details through explicit choices.
  Never merge two possessions based only on their name or embedding similarity.
- Keep cancellation, exact retries, context changes, provider permission and
  per-account isolation reliable. Report actual saved outcomes with record and
  source links. Unsupported requests should explain what is missing.
- Preserve clearly identified local/offline operations; never silently turn a
  local request into an external model call.

Acceptance: a user can add a sourced asset, update several supplied details in one
coherent request, answer a clarification, retrieve the details in a later
conversation and inspect/correct their evidence. Duplicate retries, stale context,
two same-name items, partial validation failure and another user's IDs are covered.
Verify with synthetic tests and separately authorized configured-provider checks;
mock tests alone do not establish real model quality.

The [assistant design](superpowers/specs/2026-10-21-ai-asset-assistant-design.md)
describes this first slice. v0.60.0 delivers its first increment
([AI assistant](AI_ASSISTANT.md)) and v0.61.0 adds streamed progress status;
typed template fields and live-provider verification remain.

## Phase 2: evidence intake and useful recall

Improve the existing tracking loop rather than creating disconnected extraction
screens or new domain subsystems.

- Let users ask supported questions about supplied photos/documents and save
  evidence-backed candidate details through the shared assistant/review contracts.
- Add AI price/currency/date suggestions to receipt intake using exact-money
  services, source quotes and ambiguity handling. This is purchase tracking, not
  a payment allocation or accounting ledger.
- Start existing Gmail purchase-discovery scans conversationally with explicit
  mailbox/time/purpose scope. Add bounded private attachment intake as a separate
  increment after the text/evidence loop works reliably.
  v0.62.0 lets the [AI assistant](AI_ASSISTANT.md#email-scans) queue one
  existing text discovery or evidence scan; attachment intake remains.
- Improve retrieval and source/photo navigation where representative user tasks
  reveal friction. Add OCR/formats only for demonstrated intake gaps; common
  documents already have local extraction and reviewed originals.
- Add requested, cited and dated web research for manuals/specifications when
  local evidence is insufficient, with explicit permission to send private details.
  Research does not establish ownership or guarantee parts compatibility.

Acceptance: import an original, inspect extracted candidates, save supported facts,
revisit them later, follow citations to the original and correct a mistake. Replay
the source without duplicate purchases/items or revival of rejected decisions.
Missing or conflicting evidence remains visibly unresolved. External research
retains dated sources and identity uncertainty. Ship these as separate bounded
increments; do not bundle all intake channels into one release.

## Phase 3: prove tracking is dependable

Treat this as a release gate as well as continuing work during Phases 1 and 2.

- Exercise the full create -> evidence -> recall -> correction -> restart ->
  export/recovery loop with representative synthetic possessions and two accounts.
- Retain direct correction, safe existing duplicate resolution, history and
  inspectable unknowns. Broaden undo only for operations that support safe reversal.
- Keep existing record/original exports and encrypted operator recovery verified.
  Add personal import/restore and selective deletion/retention in separately scoped
  increments where the user workflow needs them; broader privacy controls remain
  committed product work, not optional dashboard polish.
- Verify configured-provider behavior and connection recovery before claiming
  end-to-end readiness. Address session/account/credential issues when they block
  real tracking. Never use live personal data without the required authorization.
- Keep exact money, owner boundaries, provenance, migrations and recovery correct
  in every feature; they are not repairs to postpone until this phase.

Acceptance: representative tracking scenarios pass, current and historical answers
agree with saved evidence, retries do not duplicate records, and restored data
retains originals/history and user isolation. Record synthetic versus live coverage
and remaining limits. New proactive automation stays deferred until these checks
pass and the user separately selects a useful automation scope.

## Phase 4: UI beautification and usability

Give the working tracking app a dedicated visual refinement phase before expanding
into proactive life management. Preserve the existing Light/Dark/System choices,
approved palette references, accessibility and independently dockable panels.

- Establish consistent typography, spacing, alignment, surfaces, borders, icons,
  density and hierarchy using existing components and semantic theme tokens.
- Refine chat, asset lists/details, evidence/documents/photos, review, maintenance,
  Power Center, settings and graph controls as one coherent interface.
- Improve empty/loading/error/success states, forms, keyboard focus, readable
  evidence/status labels and the distinction between stated/inferred/unknown data.
- Check docked layouts and narrow screens; remove overflow, cramped controls and
  confusing navigation. Preserve drafts, selected context and working behavior.
- Use real record-backed displays; do not introduce decorative financial totals,
  unsupported integrations or invented personal information to fill a design.

Acceptance: review representative populated and empty screens on desktop and 390px
width in Light and Dark, test keyboard interaction and legibility, and rerun
affected UI checks. The core add -> inspect -> correct -> recall journey must be
easy to follow and visually consistent. Fix blocking usability problems earlier;
this phase is not permission to leave inaccessible or broken UI in prior releases.

## Conditional and deferred backlog

These are candidates to evaluate, not a queue to execute automatically after Phase 4.
Keep existing delivered functionality while deferring these extensions.

| Area | Decision and condition for revisiting |
| --- | --- |
| Maintenance recurrence/reminders | Defer new scheduling, mileage rules and notifications until manual tracking is dependable and the user chooses them. |
| Warranties/insurance | Track supplied coverage using existing sourced records first; dedicated claim packets, coverage workflows and insurance exports depend on actual use. |
| Recalls/consumables | Requested research and recorded specifications first; defer ongoing recall monitoring and automatic replenishment/reminders. |
| Subscriptions | Defer recurring-payment discovery, renewal management and cancellation workflows as a separate domain. |
| Bank statements/live sync | Optional separate expansion. Prove a need for statement-based expense tracking before choosing a live bank integration. |
| Financial reconciliation | Defer allocations, split/combined payments and refund accounting; exact purchase facts remain in core evidence intake. |
| Bulk/chained consolidation | Keep existing two-record correction; expand only when representative data makes its limits a real problem. |
| Shipment/replacement/unit extensions | Keep current safeguards and delivered workflows; add specialized behavior only for demonstrated tracking cases. |
| Photo event galleries | Defer; fix attachment/evidence navigation where it affects core tracking first. |
| Rich timelines/dashboards | Add only to answer demonstrated questions with real data; defer financial dashboards until those domains exist. |
| Extra connectors | Choose sources actually used, individually: Outlook/iCloud, cloud files, calendar/contacts/photos, local folders/scanners, retailers or devices. No connector catalog milestone. |
| More AI runtimes | Improve the three current adapters and tool use first; add another runtime only for a demonstrated requirement and supported contract. |
| Advanced asset form builder | Existing editable optional text fields first; richer widgets/required-field migrations only for proven needs. |
| Power Center expansion | Fix actionable reconnect/setup issues; defer elaborate remote probes and diagnostics without a concrete failure to solve. |
| Account/credential tooling | Maintain privacy/security and repair blocking issues throughout; device UI, linking, email changes and richer rotation tooling are scoped individually. |
| Mobile/PWA/remote access | Preserve the existing deferral of dedicated camera/mobile apps, offline/share-menu and domain/tunnel setup. |

## Execution rules

Choose the next bounded increment from the active phase, check current main and
overlapping work, and write its concrete acceptance criteria before implementation.
Do not prebuild deferred subsystems. Work sequentially in the root chat, without
agents. Preserve existing behavior, user changes, private data and credentials.

Follow repository verification, migration, versioning, source-graph and authorized
feature-release requirements. A documentation-only plan revision needs no version
bump, schema migration, source-graph refresh or Docker build. Publishing an image
never authorizes restarting the user's running installation.
