# LifeGather feature plan: tracking first

User decisions: 2026-10-21. This is the active feature priority plan. It supersedes
the future-feature ordering in PROJECT_PLAN.md and the 2026-10-18 ordered roadmap;
those documents retain architectural constraints and historical delivery evidence.
The user wants reliable tracking before proactive automation, with a dedicated UI
beautification phase. This plan changes priorities, not implemented capabilities.
User decision 2026-10-22: add a hosted multi-tenant option on Cloudflare as Phase 5
while keeping self-hosted Docker on any Linux server first-class.

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
([AI assistant](AI_ASSISTANT.md)), v0.61.0 adds streamed progress status and
v0.63.0 adds asset type assignment with typed template fields. Live-provider
verification with real OpenAI, Claude and Gemini connections is **Deferred by
Lisa (2026-10-23)**: do not pick it up until she asks for it.

v0.92.0 adds [maintenance through chat](MAINTENANCE.md#maintenance-through-chat-v0920)
over existing private tasks: one asset/task write, original statements/history,
unknown dates and stable retry receipts. Recurrence/reminders remain deferred.

## Phase 2: evidence intake and useful recall

Improve the existing tracking loop rather than creating disconnected extraction
screens or new domain subsystems.

- Let users ask supported questions about supplied photos/documents and save
  evidence-backed candidate details through the shared assistant/review contracts.
  v0.69.0 lets the [AI assistant](AI_ASSISTANT.md#photos-and-documents) read one
  attached saved photo or document, answer from it and save its details citing it.
- Add AI price/currency/date suggestions to receipt intake using exact-money
  services, source quotes and ambiguity handling. This is purchase tracking, not
  a payment allocation or accounting ledger.
  v0.70.0 adds [AI purchase-detail suggestions](MULTI_ITEM_RECEIPTS.md#ai-purchase-detail-suggestions-v0700)
  grounded in exact printed passages, with ambiguities flagged.
- Start existing Gmail purchase-discovery scans conversationally with explicit
  mailbox/time/purpose scope. Add bounded private attachment intake as a separate
  increment after the text/evidence loop works reliably.
  v0.62.0 lets the [AI assistant](AI_ASSISTANT.md#email-scans) queue one
  existing text discovery or evidence scan. v0.77.0 adds bounded attachment
  intake ([EMAIL_SCANS.md](EMAIL_SCANS.md#attachment-intake-v0770)), requested
  ahead of this gate, so limits stay conservative (supported documents only,
  4 MiB, three per email, 20 emails, reviewed in Documents). v0.97.0 adds
  JPEG/PNG/WebP photo attachments (8 MiB, saved in Photos) and scheduled
  attachment imports.
- Improve retrieval and source/photo navigation where representative user tasks
  reveal friction. Add OCR/formats only for demonstrated intake gaps; common
  documents already have local extraction and reviewed originals.
  v0.68.0 adds [search everything](SEARCH.md) in the top bar, with results that
  open the exact photo, document, source or asset, and photo-to-asset links.
- Add requested, cited and dated web research for manuals/specifications when
  local evidence is insufficient, with explicit permission to send private details.
  Research does not establish ownership or guarantee parts compatibility.
  v0.67.0 adds [web research](WEB_RESEARCH.md) in Chat for OpenAI and Claude
  connections; v0.83.0 saves a cited source to an asset as evidence on request.
  v0.88.0 lets the asset assistant recall a bounded selection of those saved
  findings with dated source citations; global research indexing remains open.

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
  v0.80.0 adds [browser end-to-end checks](END_TO_END_CHECKS.md): sign in, add an
  asset, attach a receipt photo and document, search, back up and restore into a
  second installation, on PostgreSQL. The [two-account loop](END_TO_END_CHECKS.md)
  (2026-10-23) runs add, evidence, recall, correction, server restart and
  backup/restore for two accounts in one installation and found nothing crossing
  between them.
- Retain direct correction, safe existing duplicate resolution, history and
  inspectable unknowns. Broaden undo only for operations that support safe reversal.
  v0.73.0 adds [undo](UNDO.md) for review-queue decisions (including dismissals),
  removing a photo from an item and pausing/resuming a scan schedule.
- Keep existing record/original exports and encrypted operator recovery verified.
  Add personal import/restore and selective deletion/retention in separately scoped
  increments where the user workflow needs them; broader privacy controls remain
  committed product work, not optional dashboard polish.
  v0.76.0 adds [selective deletion and retention](SELECTIVE_DELETION.md): delete
  several photos/documents at once (rows and stored files) and per-account chat
  conversation retention. v0.84.0 lets users [delete memories](MEMORIES.md#deleting-memories-v0840),
  removing their text while records made from them keep their provenance.
  v0.86.0 restores a personal archive into an account that already has records,
  adding only missing records and keeping current ones. v0.99.0 [erases a
  source](SOURCE_ERASURE.md) (a Gmail connection or one scan) and everything
  derived from it.
- Verify configured-provider behavior and connection recovery before claiming
  end-to-end readiness. **Deferred by Lisa (2026-10-23):** testing with real
  OpenAI, Claude and Gemini connections waits until she asks for it; do not pick
  it up as the next task. Address session/account/credential issues when they block
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
- Progress: v0.72.0 delivers the first [consistency pass](UI_CONSISTENCY.md):
  shared form controls, keyboard focus ring, alert/status messages, stated /
  inferred / unknown badges, page cards for Scans and Purchases and a roomier phone
  top bar. v0.79.0 finishes the second pass: asset details, the assistant's
  proposal and evidence cards, graph controls and the Assets search row use the
  same shared styles. Docking moved to drag-to-dock in v0.71.0.

Acceptance: review representative populated and empty screens on desktop and 390px
width in Light and Dark, test keyboard interaction and legibility, and rerun
affected UI checks. The core add -> inspect -> correct -> recall journey must be
easy to follow and visually consistent. Fix blocking usability problems earlier;
this phase is not permission to leave inaccessible or broken UI in prior releases.

## Phase 5: hosted option on Cloudflare, self-hosting kept first-class

User decision: 2026-10-22. Design and research: [hosted SaaS report](HOSTED_SAAS_CLOUDFLARE.md).
One codebase and one image serve both deployments. Hosted runs the image as a
Cloudflare Container behind a thin Worker with managed PostgreSQL and R2;
self-hosted keeps Docker Compose with a Postgres sidecar and local files. Hosted
behaviour is chosen only by settings; Cloudflare-specific code stays in
`deploy/cloudflare/`. Increments 5.1–5.3 also improve self-hosting and may start
once the PostgreSQL migration merges. Public launch (5.4 onward going live) waits
for the Phase 3 acceptance gate.

- **5.1 Portable container** (done in 0.78.0, see [portable container](PORTABLE_CONTAINER.md)). Image includes the `s3` extra and Postgres driver;
  vault key and settings accepted from environment variables with key IDs for
  rotation; migrations and startup file moves run as a lock-guarded one-shot job;
  separate liveness/readiness checks; trusted-proxy handling for scheme and
  client IP.
- **5.2 External background mode** (done in 0.82.0, see [outside scheduler](EXTERNAL_BACKGROUND.md)). Optional setting that disables the
  in-process scan loop and exposes an authenticated, time-bounded job tick so a
  scheduler (Cloudflare Cron Trigger or system cron) runs due schedules and jobs.
- **5.3 Isolation hardening** (done in 0.89.0). PostgreSQL row-level security as a second lock on
  owned tables, a cross-account test suite over every HTTP route and MCP tool, and
  per-user file-size and storage quotas. Row-level security, account-scoped files
  and jobs, and the cross-account suite are done in 0.81.0 (see
  [account isolation](ACCOUNT_ISOLATION.md)); the account-wide storage quota is
  done in 0.89.0 (see [storage quotas](STORAGE_QUOTAS.md)).
- **5.4 Cloudflare deployment package.** Worker, wrangler config, container pool
  routing with streamed chat, Cron tick, Secrets Store, private R2 bucket,
  Cloudflare Access on operator routes, and a setup runbook. Staging only until
  the launch gate passes.
  The test-site package is done (see [Cloudflare test site](CLOUDFLARE_TEST_SITE.md)):
  Worker and container, Cron tick, R2, Worker secrets, Access in front of the whole
  test site, and Lisa's setup runbook. Real visitor addresses through a
  Worker-signed header are done in 0.91.0. A live staging deployment and Access
  only on operator routes (once public) remain.
- **5.5 Hosted account lifecycle.** Turnstile bot checks on sign-up/password
  forms, terms and privacy acceptance, and verified account deletion across
  database rows, stored files and backup expiry; personal archive remains export.
  Account deletion across database rows and stored files is done in 0.87.0
  (see [account deletion](ACCOUNT_DELETION.md)). Optional Turnstile bot checks
  and terms-of-use acceptance are done in 0.90.0 (see
  [sign-up protection](SIGNUP_PROTECTION.md)). Backup-expiry records are done
  in 0.100.0 (see [backup expiry and restore drill](RESTORE_DRILL.md)).
- **5.6 Backups and recovery for many users.** Managed Postgres point-in-time
  recovery, protected R2 copies, a timed restore drill with written RPO/RTO, and
  per-user restore from the personal archive. The timed drill command and
  written targets are done in 0.100.0 (see [restore drill](RESTORE_DRILL.md));
  running it against the hosted database is the operator's step.
- **5.7 Google verification.** Production OAuth branding, privacy policy and the
  restricted-scope review plus yearly CASA assessment for `gmail.readonly`.
  Until approved, hosted Gmail scanning is limited to allowlisted test users.
- **5.8 Operations.** Structured logs without private content, error alerts, an
  Access-protected operator view of job backlog, failures and storage use.
  v0.94.0 delivers the logs, alerts and an operator-only
  [Operations page](OPERATIONS.md), which also shows the per-account storage
  limit.
- **5.9 Plans and billing (conditional).** Only if the hosted service charges;
  includes any platform-paid AI usage, which is otherwise not offered.

Acceptance: the same image passes smoke tests self-hosted (Compose, Postgres
sidecar, local files) and hosted (staging Cloudflare, managed Postgres, R2). Two
synthetic accounts cannot read or change each other's data with service filters
or RLS alone; schedules run with containers asleep; deletion leaves no rows or
objects; a restore drill succeeds. `AGENTS.md`'s "public SaaS infrastructure"
anti-goal is updated to reference this phase when 5.4 starts.

## Phone app plan (not scheduled)

Planned 2026-10-23 at the user's request. The user scheduled steps 6.1 to 6.3 the same
day; 6.1 to 6.3 are done. The user scheduled 6.4 (Android app) on 2026-10-23,
done in v0.101.0, and 6.5 (iPhone app) the same day, done in v0.102.0.
v0.88.1 checked the web UI at phone and tablet sizes, so the app already works in
a phone browser.

Approach: an installable web app (PWA), not a separate native app. The same
React UI and server serve phones, tablets and desktops, self-hosted and hosted
alike, with no app store review, second codebase or separate release train.

- **6.1 Install to home screen. Done in v0.95.0** ([installable app](INSTALLABLE_APP.md)).
  Web app manifest, icons and a service worker that stores only an offline
  "can't reach your server" page and its icon; it never caches the app's HTML,
  API, sign-in, file or chat responses, so new releases load as described in
  [versioning](VERSIONING.md). Installing needs HTTPS (see below). Not yet
  checked on a real iPhone or Android phone.
- **6.2 Camera capture. Done in v0.96.0** ([camera](INSTALLABLE_APP.md#taking-photos-with-the-camera)).
  On touch screens Chat and Photos show a "Take a photo" button: the ordinary
  file input with `capture="environment"`, so no custom camera code. The photo
  is saved straight away with a progress bar and Cancel; a lost response or a
  Cancel can resend the same photo, which the server stores once. Uploads keep
  the existing limits and quotas. Not yet checked on a real phone.
- **6.3 Share to LifeGather. Done in v0.98.0.** Android: manifest `share_target`, so a receipt
  photo or PDF can be shared from another app. iPhone Safari does not support
  share targets; ordinary upload stays the universal path there.
  Delivered in v0.98.0: the service worker holds shared files in memory only
  (never Cache Storage or IndexedDB) until the signed-in page claims them once;
  the page saves each through the existing Photos or Documents upload, so CSRF,
  size limits and storage quotas still apply. Without a running worker the
  server answers the share with a "share again" notice and stores nothing. Not
  yet tried on a real Android phone. See [installable app](INSTALLABLE_APP.md).
- **6.4 Android app. Done in v0.101.0** ([Android app](ANDROID_APP.md)). The user
  wanted the app on phones without setting up HTTPS (a tunnel or Tailscale was
  too much). A small Android app, installed once from an APK, asks for the
  server's home-network address (`http://<ip>:8787`) on first launch and shows
  the same web UI in a WebView, through a relay on the phone's own
  `127.0.0.1:8787` so the server's sign-in and origin checks are unchanged.
  Camera capture uses the phone's camera app; "Share to LifeGather" hands files
  to the page's existing share flow. Plain Java with no Gradle plugin, so it
  builds from distribution packages. No offline editing or local copy of
  personal records on the phone. Not yet tried on a real phone.
- **6.5 iPhone app. Done in v0.102.0** ([iPhone app](IPHONE_APP.md)). Same idea
  as the Android app, in Swift under `ios/`: server-address screen, `WKWebView`,
  loopback relay on the iPhone's `127.0.0.1:8787` (no server change), camera
  through the page's file input, and a Share extension that hands files to the
  page's existing share flow. Building and installing need the user's Mac,
  Xcode and Apple developer account (cable install or TestFlight), so the source
  ships with a plain-language guide. Not yet compiled in Xcode or tried on a
  real iPhone.

Requirement: installing and camera/share features need HTTPS on a real address.
Hosted Cloudflare (Phase 5) provides it. Self-hosted needs the user's chosen
remote-access path from [remote access](REMOTE_ACCESS.md) (for example a
Cloudflare Tunnel), which remains a separate user decision; on the home network
alone the app still works in the browser but cannot be installed as an app.

Acceptance: install on iPhone Safari and Android Chrome against both a self-hosted
HTTPS address and the hosted test site; sign in, capture, share (Android), sign
out; confirm no private response is stored by the service worker, two accounts on
one phone cannot see each other's data, and a new release replaces the cached shell.

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
| Photo event galleries | Done in v0.103.0: owner-named galleries with optional typed event dates, multi-photo add, and gallery links in photo details. See [photo galleries](PHOTO_GALLERIES.md). Automatic grouping by photo date or place stays out (previews have no metadata). |
| Rich timelines/dashboards | Add only to answer demonstrated questions with real data; defer financial dashboards until those domains exist. |
| Extra connectors | Choose sources actually used, individually: Outlook/iCloud, cloud files, calendar/contacts/photos, local folders/scanners, retailers or devices. No connector catalog milestone. |
| More AI runtimes | Improve the three current adapters and tool use first; add another runtime only for a demonstrated requirement and supported contract. |
| Advanced asset form builder | Existing editable optional text fields first; richer widgets/required-field migrations only for proven needs. |
| Power Center expansion | Fix actionable reconnect/setup issues; defer elaborate remote probes and diagnostics without a concrete failure to solve. |
| Account/credential tooling | Maintain privacy/security and repair blocking issues throughout; device UI, linking, email changes and richer rotation tooling are scoped individually. |
| Mobile/PWA/remote access | 6.1 to 6.5 done (installable app, camera, Android share, Android app in v0.101.0, iPhone app in v0.102.0). When revisited, follow the [phone app plan](#phone-app-plan-not-scheduled): installable web app first, native wrapper only if needed. Domain/tunnel setup stays a separate user decision. |

## Execution rules

Choose the next bounded increment from the active phase, check current main and
overlapping work, and write its concrete acceptance criteria before implementation.
Do not prebuild deferred subsystems. Work sequentially in the root chat, without
agents. Preserve existing behavior, user changes, private data and credentials.

Follow repository verification, migration, versioning, source-graph and authorized
feature-release requirements. A documentation-only plan revision needs no version
bump, schema migration, source-graph refresh or Docker build. Publishing an image
never authorizes restarting the user's running installation.

Research-save reliability: v0.84.1 binds each accepted request to its original input and finding, including duplicates. Exact retries preserve removal state; records format 6 preserves receipts.

Reconnect prompts: v0.85.0 remembers when Google or an AI provider refuses a saved sign-in (Gmail `invalid_grant`/`401`, AI `401`/`403`) and offers one-click Reconnect in Power Center, Scans, chat and Settings. Migration 0036.
