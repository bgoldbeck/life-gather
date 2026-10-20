# LifeGather personal discovery and recall design

Status: design baseline; implemented source milestones and remaining work are tracked in `PROJECT_PLAN.md`.

## Purpose and first useful release

LifeGather is a self-hosted personal AI assistant that maintains a private, evidence-backed model of a user's life. Chat is the primary operator interface. Graphs, lists, timelines, and dashboards support exploration and review. Direct correction, export, and recovery remain usable without an AI provider.

First release loop: sign in with Google, configure an individual AI connection, upload a receipt or nameplate photo, reconcile an item automatically, inspect its evidence and graph connections, and retrieve a useful fact in a later conversation. A small interactive graph is part of this release; elaborate dashboards are not.

## Appearance and settings

User decision, 2026-10-17: provide Light and Dark modes selectable in app Settings as part of the first usable UI. Preserve the selected preference per user. The soft cream/sage/green design in `.references/lifegather-soft-green-light-theme.png` is a pleasant reference for color and mood. Create a complementary dark palette, including semantic states, text, borders, focus indicators, charts, and graph connections, with accessible contrast in both modes. Do not rely only on color to distinguish connection/evidence status. Implement theme support alongside the early UI; the screenshot's placeholder content is not a requirement to preserve its layout or copy.

## Power Center and navigation additions

User decisions, 2026-10-20: [Power Center and dockable navigation](2026-10-20-power-center-design.md)
adds a primary Power Center destination, capability-based readiness scoring,
health/freshness checks with explanations and remedies, and precise post-connection
capability summaries. The primary navigation panel defaults left, docks at any
edge and resizes independently of the existing right-default contextual assistant.
These requirements are planned; the screenshot is illustrative, not proof of
implemented integrations. See the [current capability and remaining-work inventory](../../CAPABILITIES_AND_REMAINING_WORK.md)
for reconciled status rather than historical stage descriptions.

## Broader document support

User decision, 2026-10-20: extend the private document workflow beyond PDF to
Word (`.docx`), Excel (`.xlsx`), plain text, Markdown and CSV. Preserve original
files, source locations, reviewed-text provenance, isolation and recovery.
See [broader document support](2026-10-20-broader-document-support-design.md)
for the planned scope and acceptance criteria; these formats are not yet implemented.

## Accounts and privacy

- Any Google account can register without invitations or an email allowlist. First login creates an empty private workspace. Open registration does not itself authorize public internet deployment.
- Every user's chats, sources, graph, documents, settings, schedules, research, credentials, and connector cursors are isolated. No shared spaces or cross-user identity matching.
- Users supply their own AI, email, and bank connections. Google sign-in does not grant mailbox-reading permission. Installation-wide OAuth client configuration is distinct from users' private connector credentials.
- Services derive the acting user from authenticated context. Ownership applies to database queries, foreign-key relationships, indexes, deduplication, caches, files, jobs, exports, and MCP responses.
- Encrypt stored credentials; keep the encryption key outside the database and source control. Provide revocation. Machine administrators retain underlying storage access; application isolation is not protection from the host administrator.
- External AI processing requires the user's configured permission. Scans cannot expand that permission. Per-user usage accounting, request limits, and configurable budgets prevent uncontrolled processing.

## Evidence and identity model

Maintain separate source episodes/documents, purchase orders, purchase lines and quantities, product models, individual physical assets, assertions, evidence links, and reconciliation decisions. Use one source-independent pipeline for messages, uploads, email, bank data, and web findings.

An order, shipment, final receipt, bank charge, and conversation may support one purchase and one asset. Source deduplication and physical-identity resolution are separate operations. Scope stable source identifiers to the user and connector; scope retailer order identifiers appropriately. Represent each purchased unit separately when quantity exceeds one. Enforce trusted uniqueness and transactional writes so retries and concurrent jobs cannot double-create records.

Brand/model similarity finds candidates; it never proves physical identity. Serial identifiers need manufacturer/context and conflict checks. A payment alone does not establish item contents. Split payments, combined charges, refunds, transfers, returns, and replacements require explicit handling. Financial amounts use integer minor currency units or exact decimals with currency; graph strings and LLM arithmetic are not accounting.

Keep world-valid time separate from recorded time. Distinguish user statements, source-supported assertions, inference, and unknowns. A receipt supports a purchase but does not by itself prove delivery, current ownership, or warranty coverage.

## Automatic discovery and review

Outcomes are create, enrich, or review. Save clear new items automatically with ownership visibly inferred from the source. Attach evidence to an existing item when identity is established. Ambiguous discoveries remain outside confirmed inventory until resolved.

Discovery cards offer correction, same-as-existing, bought-for-someone-else, returned/canceled, and undo. Corrections preserve evidence and history, subject to explicit privacy deletion. Same-item consolidation preserves linked receipts, notes, relationships, and conflicts, and records a reversible decision rather than silently deleting a duplicate.

Ambiguous matches appear both in chat and a persistent review queue with synchronized state. Compare available identifiers and evidence, explain uncertainty, and offer Same item, Different items, or Not sure. Not sure leaves the case unresolved. Do not repeatedly recreate a rejected match when a source is reprocessed without new evidence.

## Chat-requested and scheduled scans

No ingestion trigger based on a newly arriving email. Users request scans in chat or configure schedules. When scope is clear and the account is connected, execute immediately without another confirmation card. Ask only for necessary missing account, time range, or purpose.

Display scope, progress, cancellation, and results. Cancellation stops further work at safe boundaries; completed transactions remain saved, and retries/resumption stay idempotent. Persist job state for recovery; avoid overlapping scheduled runs creating duplicates. Summaries link to new records, enriched records, returns/cancellations, and unresolved cases. Schedules have an explicit timezone, next-run display, pause/edit controls, and owner-scoped credentials and budgets.

## AI and tool boundaries

Implement one provider first behind replaceable interfaces; store durable memory independently of provider sessions. HTTP handles auth, uploads, chat streaming, and static files; validated MCP operations delegate to framework-independent services.

Extraction of untrusted email, web, or document content runs without write tools or credential access and emits schema-validated candidates. Deterministic services validate, authorize, reconcile, and commit. The extractor cannot invoke operational tools; the conversational agent cannot treat retrieved source text as authority to expand a task, disclose data, or approve a consequential action. No unrestricted SQL, shell, or filesystem tools for the product assistant.

## Early useful recall

[Photo evidence design](../../PHOTO_EVIDENCE.md) specifies saved originals, private galleries, graph-to-source access, manual attachment to existing items, per-user file deduplication, and claim-level evidence. Ordinary image uploads remain early scope; a dedicated phone camera flow does not.

Provide simple home and vehicle records early: model/serial, filter dimensions, maintenance, room paint information, and other supported specifications. Users can provide label photos, manuals, and corrections. Unknown values stay unknown. VIN decoding is identification, not proof of parts fitment; compatibility answers need appropriate manufacturer/parts evidence. Responsive capture and quick fact views matter for use in a store. Offline/PWA behavior is future work, not an initial guarantee.

## Delivery order and gates

1. Google registration, sessions, ownership enforcement, credential foundation, and mocked two-user isolation tests.
2. Deterministic graph/evidence services, source idempotency, temporal corrections, export, and backup/restore tests.
3. Source-independent reconciliation using synthetic receipts/messages, product versus physical-unit identity, quantities, and review decisions.
4. One-provider chat and authenticated MCP, persistent conversations, streaming, bounded execution, and per-user usage controls.
5. Receipt/nameplate capture, restricted uploads, extraction, discovery cards, direct correction, and review queue.
6. Small graph explorer, evidence/detail views, early home/vehicle profiles, and useful sourced recall. Together stages 1–6 form the first useful release.
7. User-requested email scans, then saved scheduled scans. Verify connector permissions, provider requirements, and operating costs before choosing an integration. Forwarding is an optional alternative requiring its own inbound-mail design.
8. Chat-requested web research with cited sources, dated findings, explicit task scope, and uncertain identity handling. Research permissions for sending private details remain an open product decision.
9. PDF/CSV bank statements, then live bank syncing with shared reconciliation. Validate provider availability/cost before commitment. Email precedes bank work because receipts identify products more directly.
10. Additional AI providers and discrete expansions: warranties/claim packets, insurance inventory exports, consumables, expiry dates, maintenance reminders, recalls, subscriptions, and richer dashboards. Validate each expansion separately; these suggestions are not all initial-release commitments.

## Acceptance evidence

- User A cannot retrieve, link, modify, export, or deduplicate against user B's data, including guessed IDs and background jobs.
- Importing receipt, attachment, order/shipping messages, payment, and manual statement in different orders yields one purchase and one asset when evidence establishes the same unit.
- Two genuinely distinct purchases/units of the same model remain distinct. Uncertain identity creates review work, not a second confirmed asset.
- Repeated/concurrent imports do not duplicate sources, purchases, unit mappings, or graph assertions.
- A mistaken match can be undone without losing evidence; later reprocessing respects reconciliation history.
- Untrusted documents cannot trigger tools or leak another user's data or credentials. Extraction tests run against fixed synthetic fixtures and mock providers.
- Upload an item source, ask about it in a later conversation, inspect graph evidence, correct a detail, restart, and verify persistence. Backup restoration is tested separately.
- Switch Light/Dark in Settings and verify the user's preference persists without affecting another user. Check chat, forms, review cards, evidence views, and graph readability in both modes, including keyboard focus and status indicators.
- Connector jobs honor requested scope, cancellation, schedule timezone, owner permissions, and budgets; canceled/retried jobs do not duplicate completed work.

## Operations and unresolved implementation choices

User decision, 2026-10-17: defer dedicated phone-app/camera capture, PWA/share-menu work, and remote-access setup until later. Keep responsive web UI and ordinary receipt/nameplate file uploads in the first release. Earlier mentions of photo capture mean uploaded images at this stage, not a dedicated mobile workflow. [Remote access research](../../REMOTE_ACCESS.md) remains reference material; domain selection and tunnel setup are not next steps. No domain is currently owned and no remote endpoint is enabled.

GitHub Actions stays disabled by user choice. Verify locally. Docker rebuilds and uploads need explicit approval with available image-size information; code push/merge is not approval. Source Graphify remains a development-only code navigation tool, unrelated to personal graph storage.

Choose concrete auth/session and encryption libraries, provider/model adapter, upload limits, graph library, and job persistence in implementation plans. Verify current SDK/API contracts and costs then. Do not assume packages or external services are free. No live connector setup, paid services, app implementation, or Docker publishing is authorized by this design document alone.
