# Changelog

## 0.83.1 — Compact Power Center

- Power Center is denser so your connections show without scrolling on a
  typical laptop screen (checked at 1366x768 and 1440x900 with the assistant
  docked), following `.references/lifegather-standard-dark-theme.png`.
- The hero is one short row (icon, title, Check all locally) with a slimmer
  power bar; stat tiles put the icon beside the value.
- **Your connections** now comes right after the stat tiles, with its filters
  beside the heading. Each card's scope and supported outcomes fold into
  **Scope and supported outcomes**. Health and next actions follow the
  connections. No data, API or migration changes.

## 0.83.0 — Save web research findings as evidence

- In a finished Chat web research reply, each cited source offers **Save to
  <asset>** while an asset is open. Nothing is saved until you press it. The
  server copies the source's URL, title, page date, excerpts and research time
  from the stored reply; the browser cannot supply them. See
  [docs/WEB_RESEARCH.md](docs/WEB_RESEARCH.md#saving-a-source-to-an-asset).
- Assets show **Saved web research** with the link, page date, research and save
  times and excerpts. Remove asks first and keeps the removed row as history.
  Saving is idempotent per request and per asset/page; consolidated records share
  findings; deleting the conversation keeps them.
- Findings stay labelled as describing a product model, never ownership, purchase
  details or parts compatibility, and do not change asset details.
- Read-only MCP tool `asset_research_findings`.
- Migration `0034_research_findings` adds the owner-scoped `research_findings`
  table with a row-level security policy; the cross-account isolation suite
  covers its routes and identifiers. Operator recovery accepts the new migration.
  Personal records format 5 includes findings; format 4 archives still restore.

## 0.82.2 — Smaller image uploads for app updates

- The Docker image now keeps third-party Python packages in their own layer,
  separate from LifeGather's code. That layer changes only when
  `backend/uv.lock` or `backend/pyproject.toml` does, so a typical code update
  uploads about 1 MB of backend code plus the 1.6 MB web app instead of the
  whole 57 MB Python environment. The first push after this change still
  uploads the new layers once.
- Measured on a cloud build of this revision: about 103 MB compressed in total
  (44 MB Debian/Python base, 56 MB dependencies, 1 MB app, 1.6 MB web app) and
  about 317 MB unpacked. The installed files are identical to before.
- No migration.

## 0.82.1 — Release checks run on Windows again

- Fix: the release script's backend verification (`uv run pytest`) failed on
  Windows since private file storage arrived, because it opened stored files
  with a symlink guard (`O_NOFOLLOW`) that Windows does not have. Stored files
  now refuse symlinks explicitly on Windows, and every protected file the app
  writes (stored originals, backups, recovery bundles, key files) is opened in
  binary mode so Windows never rewrites line endings inside them.
- The file-permission assertions in the storage test only run where POSIX
  permissions exist. Linux and Docker behavior is unchanged.
- No migration.

## 0.82.0 — Background scans from an outside scheduler

The in-process scan loop stays the default; nothing changes unless you opt in.
See [docs/EXTERNAL_BACKGROUND.md](docs/EXTERNAL_BACKGROUND.md).

- `LIFEGATHER_BACKGROUND_MODE=external` starts no scan loop. Due schedules and
  queued scans then run only on a **tick**, from `python -m lifegather.jobs`
  (system cron) or `POST /internal/jobs/tick` with
  `Authorization: Bearer <LIFEGATHER_JOB_TICK_TOKEN>` (Cloudflare Cron Trigger or
  any HTTPS scheduler). The endpoint answers 404 unless external mode and a token
  of 32+ visible ASCII characters are set; a wrong token answers 401, a tick
  already running on the instance 409. Responses carry counts only.
- Each tick has a time limit (`seconds`, 1–300, default 50). A scan still running
  at the limit stops after its current step, keeps its checkpoint and recovery
  attempts and resumes on the next tick. Ticks on several instances are safe
  together through the existing scan leases.
- Ticks keep the scheduler's own change attribution; a tick over HTTP is not
  recorded as a web account request.
- No migration. New settings are deployment-local and not stored in recovery
  bundles.

## 0.81.0 — Account isolation hardening

A second, database-enforced lock between accounts. See
[docs/ACCOUNT_ISOLATION.md](docs/ACCOUNT_ISOLATION.md).

- Migration `0033_account_row_security` creates the server-wide database role
  `lifegather_account`, grants it table access and turns on PostgreSQL row-level
  security for every table with a `user_id` column, plus `users`. Its policies
  show and accept only rows owned by the acting account. The database user in
  `LIFEGATHER_DATABASE_URL` must be able to create roles (the Compose superuser
  can); otherwise the migration stops with a permission error.
- Signed-in web requests and MCP calls act for their account: each database
  connection they take switches to `lifegather_account` with the account id, so
  a query that forgets its owner filter still sees only that account's rows.
  Each claimed scan job runs the same way for its owner. Startup, migrations,
  the scheduler, retention sweeps and operator recovery stay unrestricted.
- While acting for an account, file storage refuses keys outside
  `users/<account>/`.
- New cross-account test suite: a second account calls every HTTP route and MCP
  tool with the first account's identifiers; no response may contain its
  records and none of its rows may change. Guard tests fail when a new owned
  table lacks a policy or a new identifier is not covered.
- Per-user file-size and storage quotas are not part of this release.
## 0.80.0 — End-to-end reliability checks

- New browser checks (Playwright, Chromium) walk through sign-in, adding an
  asset with the duplicate prompt, attaching a receipt photo, uploading and
  reviewing a receipt document, search everything, backing up a personal archive
  and restoring it into a second installation, and sign-out. They run against
  the real backend on throwaway PostgreSQL databases with synthetic data:
  `npm run test:e2e` from `frontend/`. See
  [docs/END_TO_END_CHECKS.md](docs/END_TO_END_CHECKS.md).
- Fix: restoring a personal archive that contains a text, Markdown, CSV, Word or
  Excel document no longer fails with "Archive record is missing a required
  value". Archives downloaded earlier restore correctly with this release.
- No migration.

## 0.79.0 — Consistent asset details, assistant cards and graph controls

- The assistant panel now uses the same text boxes, menus, checkboxes and error
  callouts as the pages, so asset proposal, receipt review and note correction
  cards match the rest of the app in Light, Dark and Forest dark.
- Buttons in assistant cards and evidence views keep an even gap instead of
  touching or stacking edge to edge.
- Asset details are evenly spaced; **View original evidence** and **View in graph**
  sit together on one row, and section headings follow the shared size scale.
- The Assets search row lines up: the search box, button and "Include historical
  records" checkbox share one height.
- Graph focus controls line up with their menus, and the zoom buttons are square.
- Panel stylesheets no longer carry their own input borders, padding or focus
  rings. See [docs/UI_CONSISTENCY.md](docs/UI_CONSISTENCY.md). No migration, API
  or dependency change. Docking is unchanged.

## 0.78.0 — Portable container

Self-hosted Docker Compose keeps working unchanged; every new option is off or
keeps today's behaviour by default. See [docs/PORTABLE_CONTAINER.md](docs/PORTABLE_CONTAINER.md).

- The image now includes the `s3` extra (boto3), so S3/R2 file storage works from
  the published image.
- Vault keys can come from `LIFEGATHER_VAULT_KEYS` (`id:base64key`, comma
  separated, first is active). Listing a new key before the old one re-encrypts
  every stored credential under the new key at the next start, in one
  transaction; an instance still holding the old key then refuses credential
  writes (503). `LIFEGATHER_VAULT_KEY_FILE` still works, and beside env keys it is
  previous key `file`. Recovery bundles carry the active key.
- Startup tasks (one-time SQLite import, schema upgrade, inline-file moves, vault
  rotation) hold a PostgreSQL advisory lock, so instances starting together take
  turns. `python -m lifegather.migrate` runs them once and exits;
  `LIFEGATHER_MIGRATE_ON_START=false` leaves them to that job, and the app then
  refuses to start on an outdated schema.
- New readiness check `GET /health/ready`: 200 once started with the database at
  this release's schema, otherwise 503. `/health` stays the liveness check.
- `LIFEGATHER_TRUSTED_PROXIES` (IP addresses or CIDR networks, empty by default)
  trusts `X-Forwarded-For`/`X-Forwarded-Proto` from those peers only, so login
  rate limits see the real client behind a reverse proxy.
- No migration. New settings are deployment-local and not stored in recovery
  bundles.
## 0.77.0 — Gmail attachment intake

- New scan source **Import Gmail attachments** (`gmail_attachments`), from Scans
  or by asking the assistant (purpose `import_attachments`). Supported document
  attachments (PDF, DOCX, XLSX, CSV, TXT, MD; at most 4 MiB each, three per
  email, 20 emails per run, 10 by default) are downloaded read-only and saved as
  private documents through the normal upload path and file storage, ready for
  text review. No AI reads them and no inventory is created.
- Other files are listed on the saved email source but never downloaded.
  Replays reuse the same source, document and link; hand-uploaded duplicates are
  linked, not stored twice. Documents can open the email a file came from.
- The Gmail client allows one new read-only endpoint (message attachments) with
  a 6 MiB response cap; every other operation is still refused.
- Migration `0032_email_attachments` adds the email-to-document link table.
  Recovery accepts snapshots at this revision. See
  [docs/EMAIL_SCANS.md](docs/EMAIL_SCANS.md#attachment-intake-v0770).
- Shipped ahead of the roadmap's "after reliable text scans" gate on request,
  with conservative limits. Scheduled attachment scans and image attachments are
  not included.

## 0.76.0 — Selective deletion and conversation retention

- Photos and Documents can delete several items at once: tick up to 50, confirm,
  and they are deleted together or not at all. A changed or foreign item refuses
  the whole selection. Each original file and photo preview is removed from file
  storage right after the change is saved (retried on next start if storage is
  unreachable); reviewed text, facts and history stay. See
  [docs/SELECTIVE_DELETION.md](docs/SELECTIVE_DELETION.md).
- New **Conversation retention** setting: keep chat conversations until you delete
  them (default), or for 30 days, 90 days or 1 year after their last activity. The
  page previews how many conversations a choice removes now. Expired
  conversations without pending requests are deleted on save, on startup and
  hourly, with the existing content-free deletion receipt. Saved memories,
  sources, originals and records are never touched.
- Deletion is permanent and not undoable.
- New endpoints `POST /api/photos/delete-many`, `POST /api/documents/delete-many`,
  `GET`/`PUT /api/chat/retention`. Migration `0031_conversation_retention` adds a
  nullable `user_settings.conversation_retention_days` column; operator recovery
  accepts snapshots at this migration.
## 0.75.0 — PostgreSQL storage

- **Storage moved from SQLite to PostgreSQL.** `LIFEGATHER_DATABASE_URL` is now
  required. The Compose files add a `db` service (`pgvector/pgvector:pg17`) with
  its own `lifegather-db` volume; set `LIFEGATHER_DB_PASSWORD` before starting.
  See `docs/POSTGRESQL.md` and the TrueNAS upgrade steps.
- **One-time import.** The first start against an empty database copies an
  existing `/data/auth.sqlite3` (schemas `0027_forest_dark_theme` through
  `0029_receipt_detail_basis`, releases 0.64–0.74)
  in one transaction, checks SQLite integrity and every table's row count, and
  rebuilds search. The SQLite file is never changed; failures keep nothing.
  `python -m lifegather.legacy_import` runs the same import by hand.
- **pgvector.** Migration `0030_pgvector` enables the `vector` extension for
  future embeddings; nothing uses it yet.
- Encrypted recovery bundles are now format 2 with a portable logical database
  snapshot, and restores load a new, empty PostgreSQL database named by
  `LIFEGATHER_DATABASE_URL`. Format 1 (SQLite) bundles still verify and restore.
- Behavior is unchanged: integers stay 64-bit and text unbounded, snapshot reads
  use `REPEATABLE READ`, serialized writers take an advisory lock in place of
  SQLite's write lock, search matches whole words ignoring case and accents, and
  the database must use the `C` collation so ordering and paging stay identical.
- Backend tests run against PostgreSQL (`LIFEGATHER_TEST_DATABASE_URL`, or an
  automatic temporary cluster). The release script starts throwaway PostgreSQL
  containers for the tests and container smoke; the test-login preview gains a
  `lifegather-preview-db` sidecar.

## 0.74.0 — Restore your records

- New **Settings → Restore your records**: bring a personal archive ZIP
  (`lifegather-personal-archive/1`) back into an account with no saved records,
  for example after moving to a new installation. See
  [docs/PERSONAL_ARCHIVE.md](docs/PERSONAL_ARCHIVE.md#restoring-an-archive).
- Every member, hash, field and type is checked first; the restore is all or
  nothing. Records keep their original IDs, sources, history, corrections, exact
  money and dates. Originals go to file storage (local or S3), photo previews are
  regenerated and search is rebuilt.
- Refused when the account already has records or the records already exist in
  the installation; IDs are never rewritten. Settings, credentials and schedules
  are not in archives.
- New endpoint `POST /api/import/archive` (authenticated, CSRF-protected, 64 MiB).
  No MCP tool, migration or new dependency.
- Starter asset types saved in a restored archive are no longer listed twice.

## 0.73.0 — Broader undo

- The review queue shows **Undo** right after an identity decision. Undo returns
  the match to the queue as a new recorded decision; the undone decision and its
  audit stay in history. Dismissed matches can now be brought back, which was not
  possible before. Undo is refused once the decision has changed since, and an
  exact retry returns the same result.
- Removing a photo from an item offers **Undo**, which attaches the same photo
  again. Pausing or resuming a scan schedule offers **Undo** to switch it back.
- New private endpoint `POST /api/reviews/identities/undo` and MCP tool
  `identity_review_undo` share owner, session and CSRF checks. A new
  `identity_review_undone` audit event records each undo.
- Deleting photos, documents or conversations, disconnecting mailboxes and
  removing AI connections stay permanent. See [docs/UNDO.md](docs/UNDO.md). No
  migration or dependency change; queries are portable to PostgreSQL.
## 0.72.0 — Consistent controls, focus and statuses

- Text boxes, menus, note fields and file pickers look the same on every page:
  one height, border, corner radius and spacing. Checkboxes sit on one line with
  their label instead of floating above it.
- Every button, link, disclosure and field shows the same visible focus ring when
  reached with the keyboard, in Light, Dark and Forest dark.
- Error messages appear as a tinted callout; status and loading messages use the
  muted text color.
- Stated, inferred and unknown details show as small badges (dashed for inferred),
  on asset details, profiles, typed asset fields and record comparison.
- Scans and Purchases sit on the same bordered page card as the other pages.
  Related buttons and filters (Assets, Review, Purchases) no longer touch, and
  buttons in stacked forms keep their natural width.
- On phones the top bar drops the "Your personal space" label and the account
  name so search has room. Nothing scrolls sideways at 390px.
- See [docs/UI_CONSISTENCY.md](docs/UI_CONSISTENCY.md). No migration, API or
  dependency change. Docking is unchanged.
## 0.71.0 — Drag-to-dock panels

- Navigation and the assistant now dock by dragging: grab a panel's header and
  highlighted drop zones show the left, right, top and bottom edges; the panel
  snaps to the zone nearest the pointer when released. Escape cancels a drag.
- Small dock buttons in each panel header replace the old **Dock** dropdowns, so
  docking still works by keyboard, touch and screen reader.
- Collapsing leaves a thin rail on the panel's own edge instead of hiding it:
  navigation keeps every destination as an icon, and the assistant keeps an
  expand button. Previously the collapsed assistant always moved to the bottom.
- Saved layouts keep working unchanged; navigation gains an optional collapsed
  flag. Narrow screens keep the top navigation / bottom assistant fallback with
  dragging off. See [docs/NAVIGATION.md](docs/NAVIGATION.md). No migration, API
  or dependency change.

## 0.70.0 — AI price, currency and date suggestions for receipts

- On a confirmed receipt's purchased line, **Purchase details → Suggest with
  AI…** asks your selected OpenAI, Claude or Gemini connection to suggest the
  line total, currency and purchase date. It sends only that receipt's saved
  text, needs external-AI permission and uses one of the 20 daily AI requests.
- Every suggestion is checked against the receipt before you see it: each
  value must be printed inside an exact quoted passage, and the total must be
  on that item's own line. Anything else is dropped. Doubts are listed instead
  of guessed: a bare `$` (USD, CAD or AUD), no printed currency, `10/11/2026`
  style dates that read either way, several amounts or dates, and dates next to
  delivery, shipping or return wording.
- Suggestions only fill the editable draft. Saving is still your explicit,
  revisioned decision. A new "I checked the currency and date reading" option
  (set automatically when you copy a suggestion) lets a revision use printed
  values such as `$349.00`, `€349,00` or `Oct 11, 2026`; the server re-checks
  them against the passage and refuses a currency that contradicts it. The
  strict `Line total: USD 49.90` / `Purchase date:` rule is unchanged.
- Migration `0029_receipt_detail_basis` records each revision's basis
  (`labeled` for all existing rows, or `reviewed`). Downgrade is refused while
  reviewed revisions exist. Recovery bundles at the new head are accepted.
- New authenticated `POST /api/receipts/details/suggest`; MCP
  `receipt_details_save` accepts the optional `basis`. No new dependency.
  Live provider quality is not verified by the synthetic tests.

## 0.69.0 — Ask about photos and documents

- The AI assistant can read one attached saved photo or document, answer
  questions about it and save details found in it to one asset. Details found in
  the file cite its own source, so evidence links open the original. See
  [docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md#photos-and-documents).
- A photo without a saved transcription is sent to the selected provider once;
  the transcription is saved as the photo's source and reused. Saving from a
  photo also adds it to the asset's gallery. A document's extracted text becomes
  its source only when a detail cites it.
- Saved values must appear exactly in the user's words or the file text; the file
  never establishes ownership, the asset or its type. Another account's files are
  refused before any AI request.
- Chat requests accept an optional `document_id` in AI assistant mode, and
  `photo_id` is now also used there. No migration or dependency change.

## 0.68.0 — Search everything

- A search box in the top bar finds assets, people/places and other records,
  photos, documents and saved source text in one place, grouped by kind. Every
  word must match; `%` and `_` are literal. Choosing a result opens it on its own
  page: Photos, Documents and Memories now open straight to the chosen photo,
  document or source, and a source from a photo or document opens that original.
  See [docs/SEARCH.md](docs/SEARCH.md).
- A photo's details list the assets it is attached to, each with an **Open**
  button.
- Merged duplicate assets appear once; superseded note versions and deleted
  photos/documents are left out.
- New read-only endpoints `GET /api/search` and `GET /api/photos/{id}/assets`.
  Matching uses portable case-insensitive SQL, not SQLite full-text search, so it
  carries over to PostgreSQL storage unchanged. No migration or dependency change.

## 0.67.0 — Web research for manuals and specifications

- New Chat action **Research manuals on the web**: on request, the selected OpenAI
  or Claude connection uses its provider's web search to find manuals,
  specifications and parts information. See [docs/WEB_RESEARCH.md](docs/WEB_RESEARCH.md).
- Only the text you type is sent. The open record's saved name and details are
  added only when you tick the share box for that request; the box clears after
  each request and when the record changes, and a record edited after you looked
  at it is not sent. No other memories, photos, documents or email are sent.
- Replies keep when the research ran, the searches the provider reported, whether
  record details were shared, and each cited source's link, title, page date (or
  "date not reported") and excerpt. An answer without a valid web citation is
  discarded. Every reply notes that web results describe a product model, not
  your item, and do not establish ownership or parts compatibility.
- Research saves nothing to your records; the reply stays in the conversation.
  Gemini connections are refused for research before any usage is counted.
  Provider web-search charges apply and count as one of the 20 daily AI requests.
- No migration or data change. The Chat turn API accepts `mode: "research"` with
  `research: {"share_record": bool}`.

## 0.66.1 — Tighter workspace gutters

- Pages now fill the space between the navigation and the assistant instead of
  sitting in a centred fixed-width column, removing the empty band beside the
  sidebar on wide windows. Settings sections use the same full width.
- Narrower default navigation (244px → 216px; **Reset navigation layout**
  applies it to a saved layout), a shorter top bar, and 20px page gutters
  (12px on phones).
- On phones the top bar stays on one row; the build label is hidden there.
- Layout only. No API, data, migration or dependency change.

## 0.66.0 — Private file storage

- Original documents, photos and photo previews are now kept in private file
  storage instead of inside the database, behind one storage interface with two
  backends chosen by configuration: a local directory (default `/data/files`, on
  the existing `/data` mount) and an S3-compatible private bucket for a future
  hosted setup (`LIFEGATHER_STORAGE_BACKEND=s3`, optional `s3` extra). See
  [docs/FILE_STORAGE.md](docs/FILE_STORAGE.md).
- Every file read is checked against its recorded size and SHA-256; deleting a
  document or photo removes its stored files, retrying on the next start if
  storage was unreachable.
- Migration `0028_object_storage` adds storage key columns. Existing files keep
  working: on startup each one is copied to storage, verified and only then
  cleared from the database, one row at a time. Downgrade is refused while files
  live in storage.
- Personal archive downloads read through storage. Encrypted recovery bundles keep
  the same format and stay self-contained: stored originals are copied back into
  the snapshot and verified; a restored app moves them out again.
## 0.65.0 — Colorful icons and visual flair

- Every navigation page has its own icon in a colored tile (Power Center bolt,
  Photos camera, Scans mail, Purchases receipt, Maintenance wrench and so on);
  the current page lights up in its color.
- One small set of category colors is shared across the app and defined for
  Light, Dark and Forest dark, so color stays meaningful rather than chaotic:
  amber for power and attention, red for email, blue for finance, sky for
  documents, pink for photos, green for assets, orange for maintenance, violet
  for AI and memories, teal for graph and profiles, slate for settings.
- Power Center opens with a forest-scene banner and a glowing growth power bar
  (Seedling, Sapling, Growing, Thriving, Flourishing) driven by the existing
  capability score; an incomplete score shades its unverified range, and a stale
  snapshot greys the bar out. Stat tiles, source cards and capability rows carry
  category icons, and status pills are color-coded (ready, needs setup,
  needs attention, unverified, disabled, planned).
- Overview feature cards and illustration nodes use the same colors.
- Presentation only: no API, data, migration or dependency change.

## 0.64.0 — Standard dark theme

- Add a new standard **Dark** theme based on the user's reference: deep navy and
  slate surfaces, teal accents and bright text. System uses it when the device
  prefers dark. Text, focus and status colors meet WCAG AA contrast.
- The original green dark palette is now **Forest dark**, still selectable in
  Settings › Appearance.
- Migration `0027_forest_dark_theme` widens the theme constraint and moves every
  saved `dark` choice to `forest-dark`, so nobody's current look changes; the
  downgrade maps it back. The appearance API now also accepts `forest-dark`.

## 0.63.1 — Workspace layout polish

- Workspace pages now sit on clearly bordered surfaces: Assets, Review,
  Maintenance, Memories, Graph, Documents, Photos and Profiles each render as one
  card, and Settings sections share one aligned column with even gaps.
- Page headings and intro text use one consistent size and muted style; empty
  lists show a dashed, centred empty state instead of stray text.
- Less dead space: compact navigation rows (the full list fits without
  scrolling), a shorter top bar, tighter page padding and 14px body text.
- The assistant dock has its own surface with a centred empty prompt; resize
  handles no longer draw a second grey bar beside panel borders and still
  highlight on hover and keyboard focus.
- Theme-agnostic: only existing color tokens are used, so light and dark themes
  inherit the changes. No API, data, migration or dependency change.

## 0.63.0 — AI assistant asset types and typed fields

- The AI assistant can list your asset types, assign a current type when you name
  it ("it's a vehicle") and save that type's field values, such as tire size or
  filter specification, together with other details on one asset. Reading an
  asset now reports its type and type field values by name.
- Type IDs must come from this request's type list or asset read; values must
  appear exactly in your words; fields must belong to the assigned or chosen type.
  Unnamed, unknown, retired or foreign types, retired fields and fields from
  another type are refused. A VIN still uses the standard VIN detail.
- Type assignment, type fields, other details and the turn receipt commit
  together or not at all; a changed type keeps its earlier assignment in history.
  History records the ai assistant method and receipts link each source.
- Uses the existing asset-type services; no migration, dependency or HTTP/MCP
  contract change. Synthetic provider tests only. See [AI assistant](docs/AI_ASSISTANT.md).

## 0.62.0 — Start Gmail scans from the AI assistant

- Ask the **AI assistant** to find purchases in, or import evidence from, a
  connected Gmail mailbox for a stated period. It lists your mailboxes and queues
  one existing purchase-discovery (with the assistant's AI connection/model) or
  evidence-only scan; **View email scan** opens it.
- The host checks that your words state the purpose and period, resolves at most
  31 past UTC days, requires the address when several mailboxes are connected,
  and keeps 20 messages unless you state a limit up to 50. Existing mailbox,
  permission, busy and daily-limit checks apply; the scan is queued atomically
  with the completed turn, and replays or stopped requests never add a run.
- No migration, dependency or scan-handler change. Synthetic provider tests only.
  See [AI assistant](docs/AI_ASSISTANT.md#email-scans).

## 0.61.0 — AI assistant progress status

- AI assistant requests now stream short LifeGather-written progress lines while
  they run: understanding the request, searching assets, reading current details,
  checking details before adding or saving, and preparing a question or reply.
  Chat shows the latest line in its live status area.
- Status lines are fixed host phrases at real tool-loop stages. No model output,
  reasoning or draft reply is streamed, and no status says a save happened; the
  saved outcome still arrives only in the committed turn with its receipt links.
- The existing private stream endpoint now accepts `assistant` as well as `ask`;
  other modes are still refused there. Replay, cancellation, context and
  permission checks are unchanged. No migration, dependency or provider-contract
  change. Synthetic provider tests only. See [AI assistant](docs/AI_ASSISTANT.md).

## 0.60.0 — AI asset assistant

- Add an **AI assistant** Chat action that uses the configured OpenAI, Claude or
  Gemini connection to search and read your assets, add one owned asset with its
  supplied identifiers and details, or save several details on one asset in a
  single request. It asks when ownership, identity or a value is unclear.
- The host validates every write: values must appear in your words, ownership needs
  your own statement, duplicates need your answer, and all fields commit together
  with the completed turn or not at all. Stale records, conflicting current
  statements, unknown or foreign IDs and extra actions are refused.
- Replies after writes are server-generated receipts with Open/source links.
  Replays never call the model again; stopping before commit prevents the write.
  Pending questions live in the turn result and expire after the next message.
- The existing offline commands remain as **Local assistant (no AI)**. Change
  history records the new `ai_assistant` method with provider/model.
- No migration or dependency change. Synthetic provider tests only; live model
  quality is unverified. See [AI assistant](docs/AI_ASSISTANT.md).

## 0.59.0 — Editable private asset types and typed manual entry

- Provide Vehicle, Appliance, Electronics, Furniture and Tools & Equipment defaults,
  plus private custom/copyable types. Rename, arrange, add and retire optional text
  fields with stable IDs, immutable definition revisions and stale-edit protection.
- Select a type in manual entry; save supplied values atomically with the existing
  duplicate/identity choice and stated ownership. Inspect, explicitly reassign and
  correct sourced fields on existing assets without erasing original facts/history.
  Consolidation preserves member type conflicts and original correction subjects.
- Authenticated HTTP and MCP share validation and owner isolation. MCP can list,
  inspect, create/edit types, add typed assets and inspect/edit sourced asset fields.
  Stable requests permit safe retries; no AI provider is needed or contacted.
- Migration `0026_asset_types` adds three owner-scoped definition/field/revision
  tables; existing custom predicates and physical records are unchanged. Personal
  records format 4 adds these definitions to JSON/ZIP; operator recovery validates
  and preserves them. Unused default definitions are virtual until edited/used.
- Text fields are descriptive; no new accounting semantics, automatic compatibility,
  inferred values, required-field migration, ingestion or live redeployment.
- The preview launcher names new containers `lifegather-preview-v<actual-version>`
  from the downloaded image's OCI label and starts its inspected immutable ID.
  Recognize legacy/versioned names, refuse multiple previews or invalid metadata,
  and retain storage/settings protections and pull-before-stop ordering.

## 0.58.1 — Detect stale browser UI after deployment

- Revalidate startup HTML and other non-hashed static files on ordinary reload;
  only successful content-hashed Vite assets receive immutable caching. Preserve
  API no-store and private static/data isolation, including conditional responses.
- Embed frontend version from the single backend version source and the Docker
  revision argument. Keep the displayed version tied to the executing UI bundle;
  focus/minute session checks detect a changed server build and offer Reload.
  Explain unsaved draft loss; never reload automatically or erase drafts on checks.
- No schema, dependency, permissions or ingestion change. Existing tabs running
  pre-fix code need one reload to acquire this behavior. No running-app redeployment.

## 0.58.0 — Power Center capability readiness and observed health

- Add a primary Power Center with source/category filters, real seven-day scan
  activity, freshness, local refresh and actionable scan/setup links. Distinguish
  missing permission, AI limits, expired scan leases, failed runs, overdue dispatch
  and intentionally paused schedules.
- Scoring catalog 1 counts eight weighted outcomes once across redundant sources.
  Unknown/stale dependencies leave the total incomplete with confirmed/possible
  bounds. Saved credentials never establish model health; earlier-grant scans
  cannot establish a reconnected mailbox's health.
- Settings explains newly requestable, already available and still-blocked
  capabilities using per-account tab capability IDs only. Availability does not
  mean completed discoveries. Preserve assistant drafts and navigation docking.
- Authenticated HTTP/MCP share one read-only service. Automatic local checks never
  decrypt credentials, contact providers, incur charges or start ingestion.
  Live model availability and remote revocation before a failed run remain unknown.
  No migration or dependency; schema head remains 0025.

## 0.57.0 — Dockable, resizable primary navigation

- The navigation sidebar defaults left and can dock at any of the four edges.
  Resize its divider with pointer drag or arrows/Home/End; Shift uses a larger
  keyboard step. Horizontal docks reflow destination labels and keep overflow
  within navigation. All existing destinations remain available.
- Remember separate width/height and position per account in this browser;
  validate saved values, clamp to the viewport and offer Reset navigation layout.
  Compact screens use top navigation without overwriting the desktop preference.
- Keep the current page, unsaved assistant draft and independent assistant layout
  while moving navigation. No migration, backend domain/API or dependency change;
  Power Center itself remains a separately planned feature.

## 0.56.0 — Word, Excel, text, Markdown and CSV evidence

- Documents now preserves and locally extracts DOCX, XLSX, TXT, Markdown and CSV
  alongside PDF. Review before saving searchable text; preserve source locations,
  original bytes, correction history and private owner boundaries.
- Add worksheet/range and encoding/CSV delimiter/header previews, with an explicit
  action to replace a review draft. Formula text and possibly stale/missing cached
  values remain distinct; no macros, formulas, links or document instructions run.
- Bound Office archive/XML expansion and reuse isolated parser time/memory limits.
  Main-body Word extraction, raw Excel cell values, 4,000-character text and selected
  range limits are explicit; legacy Office, encrypted/macro-enabled files and OCR
  remain unsupported. No external model call or new dependency.
- Migration 0025 preserves existing PDFs and adds format/parser metadata. Refuse
  lossy downgrade with non-PDF records. Original downloads and private ZIP archives
  retain correct extensions/MIME; encrypted recovery accepts and verifies the new
  schema while retaining older supported snapshots. No running app redeployment.

## 0.55.1 — Current maintenance evidence in recall

- When keyword search or Ask AI finds an older maintenance statement, include
  its current source first and label the original revision as historical. Typed
  state and explicitly unknown dates stay separate from old completion text.
  Retain the existing evidence count and byte limits; omitted current evidence
  cannot establish the current state from a historical statement.
- Share owner-bound revision metadata across chat, source inspection and MCP.
  Source namespaces alone grant no task authority. Preserve original entity IDs
  and display current identity after consolidation/reversal.
- Label current/earlier maintenance statements in the source viewer and offer
  an explicit current-statement link while retaining the original text.
- No migration, dependency, provider schema, consent or model write-tool change.

## 0.55.0 — Sourced maintenance tasks and due dates

- Add manual maintenance tasks to existing asset/place Profiles, with explicit
  unknown or stated calendar dates, an IANA timezone and open/completed/canceled
  states. The global Maintenance view lists current revisions, dated tasks first,
  and links back to the correct profile. Due status uses each task's local date.
- Preserve every original statement and immutable revision. Fresh edit versions,
  serialized writes, exact request retries and monotonic recording times protect
  completion, cancellation, reopening and corrections. Earlier dates and states
  remain in history; completion dates are never automatically filled.
- Preserve original linked record IDs through consolidation and project current
  identity on reads. Bounded comparisons include task statements; task changes
  invalidate stale consolidation/reversal checks. Empty comparisons retain the
  previous token contract for existing identity receipts.
- Migration `0024_maintenance` adds owner-constrained typed task/revision tables.
  Personal records format 3 explicitly includes both collections; ZIP format 1
  continues with the current records payload. Downloads accept records formats
  1/2/3. Recovery accepts migration 0023 and 0024 snapshots and validates current task
  storage. Back up before an operator downgrade, which removes the new task tables.
- Add private HTTP/MCP adapters and responsive source/history views. No new
  dependency, automatic recurrence/notifications, maintenance recommendation,
  model write tool, provider call or existing-installation deployment.

## 0.54.0 — Reviewed private conversation deletion

- Add an explicit review action in Your conversations, showing the saved request
  count and retention scope before permanent transcript deletion. Require a fresh
  owner-scoped version token and explicit confirmation; changed conversations
  require review again. Stop pending/interrupted chat requests as a separate action.
- Remove only that conversation and its requests/replies. Retain independently
  saved memories, profile corrections, files, purchases, scans, settings, credentials
  and usage. Existing exports, backups and provider-side history remain unchanged.
  A minimal content-free deletion audit permits safe replay.
- Serialize terminal chat transitions with cancellation/deletion, fixing a
  reproduced late-completion race that could overwrite a successful stop. Preserve
  unsent drafts and other conversations; ignore late loads and stale pagination.
  No migration, dependency, provider request, model/MCP deletion tool or deployment.
  Migration remains 0023.

## 0.53.0 — Custom details through the contextual assistant

- Save explicitly supplied named details with commands such as `Set custom "Tire
  size" to 205/55R16`, using the selected private record, original request evidence
  and the existing profile name/value validation and correction history.
- Preserve explicit quoted names, exact values, version checks, conflict review,
  atomic chat replies, cancellation and stable retries. Unknowns and valid dates
  remain available through Profiles; no model write tool or inferred field/value.
- Fix direct organizer/MCP retries of corrections inherited from a consolidated
  member. Check owner-scoped current membership while retaining original subjects;
  reversal cannot authorize another physical record. No migration or dependency;
  migration remains 0023.

## 0.52.0 — Personal records and original-file archive

- Add explicit Include original photos and PDFs (ZIP) to the private Settings
  download. Package the unchanged records JSON, active owned originals and a
  versioned length/hash manifest from one real SQLite read snapshot.
- Stream and verify saved BLOBs, retain fixed safe UUID paths and preserve original
  filenames as metadata. Exclude deleted originals, previews, credentials and
  installation state. Enforce 64 MiB total including ZIP overhead, 1,000 originals
  and existing record limits before returning a complete file.
- Preserve default JSON compatibility, source/history, units and exact money;
  handle refusal, busy/duplicate clicks, aborts/late responses, safe filenames and
  file-signature validation. No dependency, migration, AI tool, provider request
  or application restore/activation. Migration remains 0023.

## 0.51.0 — Named custom sourced profile details

- Add Custom detail to Profiles for named descriptions such as tire size or fuel
  type. Require original evidence and an exact value or explicit unknown; preserve
  valid-world dates, recorded history, safe retries and selected-version corrections.
- Keep custom names separate from built-in identity fields. Normalize bounded
  names and show readable labels across Profiles, Assets, Graph, comparison and
  field history. Correcting a detail preserves its original field and subject.
- Reuse private immutable facts, canonical consolidation, selected-record recall,
  record export and encrypted recovery. Existing built-in payloads and bounded
  chat writes remain supported. No schema, dependency, export-format, provider
  request or deployment change; migration remains 0023.

## 0.50.1 — Recovery independent of lost operational settings

- Verify and restore valid bundles even when remaining environment or dotenv
  settings contain an incomplete Google/SMTP configuration or invalid old public
  URL. These commands need the bundle, not the old operational configuration.
- Preserve data/static path settings and private staging guards. Backup continues
  validating and capturing the actual installation settings. No format, schema,
  dependency, application startup or deployment change.

## 0.50.0 — Encrypted operator backup and recovery

- Add explicit local `python -m lifegather.recovery backup|verify|restore`
  commands, using a consistent SQLite snapshot and authenticated streaming
  encryption. Include all owners, original photo/PDF bytes, authentication state,
  installation settings and the original vault key when configured.
- Validate format, lengths/hashes, SQLite integrity/foreign keys, supported
  migration, original files and owner-bound credential decryption before restoring
  into an exclusively new private directory. Preserve IDs, evidence/corrections,
  consolidation history, distinct units and exact monetary records.
- Add explicit private JSON installation configuration for lossless restored
  secrets; constructor/environment/dotenv settings retain precedence. No HTTP,
  MCP or AI recovery tool, new dependency, schema change, provider request or
  automatic application activation. Migration remains 0023.

## 0.49.0 — Right-default resizable assistant

- Default the assistant to the right edge when no account preference exists;
  preserve previously saved positions and the narrow-screen bottom layout.
- Drag the page/assistant divider or use its keyboard arrow/Home/End controls
  to resize. Remember bounded width and height separately per account in this
  browser, preserving drafts, navigation, and collapse/expand behavior.
- No dependency, backend API, schema or migration change. Layout storage contains
  preferences only; no messages, personal records or provider calls are added.

## 0.48.2 — Load release images before container verification

- Explicitly load the single-platform Linux build into the local Docker engine.
  Docker container builders otherwise retain it only in cache, causing the
  isolated pull-disabled smoke test to fail with an absent image. Preserve all
  verification, source/authentication checks and separate upload controls.
- Add offline coverage for builders that require explicit image loading.
  No domain, dependency or schema change.

## 0.48.1 — Reliable scan focus verification

- Wait for React's asynchronous result-focus effect in the saved Chat scan test,
  retaining the focus and read-only assertions. This prevents an intermittent
  release-check failure; application behavior and schema remain unchanged.

## 0.48.0 — Reversible two-record asset consolidation

- Choose a primary record after a fresh complete bounded comparison and explicitly
  confirm that two records describe the same physical item. Preserve original
  entity IDs, evidence, conflicting fact versions, aliases, photo links, receipts
  and purchase identities; no financial claims are added or allocated.
- Current Assets, Profiles, galleries, graph, field history and chat recall use a
  shared identity projection. Later discovery enriches the selected primary.
  Historical recorded-time reads preserve the identity known at that time.
- Refuse overlapping groups, chains, sibling receipt units, replacement items and
  conflicting manufacturer/serial/VIN identifiers. Atomic preview/version checks,
  owner constraints, request replay and append-only explanations protect decisions.
  Guarded reversal refuses dependent changes rather than overwriting them.
- New private HTTP/MCP operations require direct human choices and remain outside
  the application's model tool set. The UI preserves uncertain request identities
  and distinguishes successful saves from failed read-only reloads.
- Add migration 0023_asset_consolidation with owner-constrained group history and
  unique active members. JSON portability format 2 adds consolidation history;
  original bytes remain excluded and the file is not a restorable backup.
- No new runtime dependency, live provider call or running-installation deployment.

## 0.47.0 — Download private records with preserved history

- Settings can explicitly download a versioned JSON copy of saved evidence,
  graph statements/provenance/corrections, reviewed purchase quantities and exact
  money, conversations and photo/PDF metadata with extracted text.
- One owner-scoped read snapshot preserves original IDs, status, unknowns, dates
  and historical claims. Fixed projections exclude account/authentication data,
  stored credentials, settings, connector/scan configuration and processing caches.
  Binary originals/previews are excluded; this is not a restorable backup.
- Refuse the entire file above 10,000 rows or 16 MiB. No partial downloads or
  server-side temporary copies. Require session/origin/CSRF and safe attachment
  headers. UI validates file format, freezes duplicate clicks, handles failures
  and ignores late responses after leaving Settings; release download URLs.
- No schema migration, dependency, AI/provider call or deployment change.

## 0.46.0 — Manual inventory and a persistent contextual assistant

- Add asset directly from Assets with a name, optional manufacturer/model/serial
  and notes, and an affirmative current-ownership declaration. Original values are
  retained as manual evidence and stated facts, never independent verification.
- Preview identity matches using the shared reconciliation rules. Link explicitly
  to an existing item or deliberately create a separate physical item. Reliable
  serial matches block duplicate creation; ownership corrections remain effective.
  Later receipts can enrich the same manual item through its canonical bindings.
- Atomic saves retain provenance and safe retry identities, with private HTTP/MCP
  adapters. Keep these write tools outside the app's provider tool allowlist.
  No migration, schema, dependency, price/date inference or live-provider calls.
- Keep Chat mounted across pages in a collapsible edge dock, with bottom docking
  by default and account-scoped layout preferences. Show the selected record.
- Explicit local commands open uniquely named assets and save supplied profile
  details with provenance, stale-version checks and atomic saved replies. Ambiguous
  names require a choice; missing VINs are requested rather than invented.
- Pin each message's record before sending; delayed replies and saved history
  cannot redirect a user who moved elsewhere. Ask AI gains bounded sourced recall
  for the selected record. MCP context stays explicit and owner-scoped; no browser
  bridge, unrestricted model writes or additional migration is introduced.

## 0.45.0 — Sourced field history and workflow attribution

- Profiles, Assets and Graph can explicitly load private paged field history:
  exact values, explicit previous versions, statement status, recorded/valid dates,
  source excerpts and links. Independent statements remain separate.
- Existing audit events now retain server-owned interface, initiation and workflow,
  with provider/model where known for AI extraction/discovery. Scheduled scan
  initiation survives worker recovery; reviewed suggestions retain their original
  proposal attribution separately from the review itself. Retries do not relabel
  earlier events. No credentials or document-supplied provenance are accepted.
- Migration `0022_change_origins` adds a nullable audit column and owner/target
  lookup index. Older origins stay unknown; no guessed backfill or fact rewrite.
  Existing source/action histories remain. The history UI covers graph facts;
  custom asset forms/templates and universal undo remain future work.

## 0.43.0 — Request email evidence scans from Chat

- Choose a connected Gmail mailbox, past UTC dates, optional filter and up to
  50 messages in Chat, then explicitly start the existing text-evidence import.
  The action needs no AI connection or permission and creates no inventory.
- Save the queued job and completed Chat result atomically. Retries reuse the
  exact scope and job; cancellation before enqueue creates no job. Old Chat
  request identities remain compatible. Ordinary messages cannot enqueue scans.
- Open the exact owner-scoped job in Scans for progress, evidence and cancellation.
  Leaving Chat does not cancel an independently queued job. Existing mailbox
  permission, one-active-run and daily scan limits apply.
- Preserve unsent text and reset scope on conversation/action changes. Freeze
  uncertain retry inputs and ignore stale mailbox reads. No schema migration,
  dependency, provider-adapter, scheduled-scan or deployment change.

## 0.42.0 — Review multiple items from receipt photos

- Explicit Chat receipt-photo action uses a saved/uploaded private original and
  the existing provider permission, budget and safe retry controls. Save the first
  unverified transcription and validated receipt draft atomically, up to eight
  lines and twenty total physical units; no inventory or accounting writes by AI.
- Reuse existing receipt reviews without another model request. If a photo has
  already been transcribed, use its current text after any active single-item
  review is resolved. Preserve the original transcription and correction history.
- Existing receipt review retains exact quotes, quantities, distinct units,
  conflicts, photo links and optional manually reviewed money/date claims. Photos
  can also display a saved receipt review returned by its existing reading action.
- Reject shortened quotes that hide a conflicting explicit quantity on the same
  source line, including repeated ambiguous passages. Old accepted records remain;
  affected pending reviews need a complete supporting quantity passage.
- Add Chat mode `extract_photo_receipt`; existing request modes stay compatible.
  No schema migration, dependency or provider-adapter change.

## Release tooling — safe source recovery

- Fetch GitHub main before release checks; fast-forward only a clean, behind local
  main and reload the updated publisher once before reading version/build metadata.
- Preserve local-only/diverged commits, staged/untracked edits and deliberate
  feature/detached builds. Explain blocked source/network states before building.
- Optional `-RepairAuthentication` starts GitHub browser sign-in/scope recovery;
  valid credentials are reused and browser authorization remains with the user.
- Host tooling only: no application version, schema or runtime image change.

## 0.41.0 — Upload private photos directly in Chat

- Explicitly save a JPEG/PNG/WebP original from Chat, up to 8 MiB, with a photo,
  receipt or nameplate purpose. Select the saved original without an eager AI
  request, conversation creation, asset attachment or inventory write.
- Preserve text drafts and the existing explicit AI submit, consent/model/budget
  and human-review gates. Originals remain in Photos when leaving Chat.
- Freeze the original file/purpose for uncertain upload retry; reuse the existing
  owner-scoped active content-hash deduplication. Ignore late upload results when
  the picker closes. Library paging deduplicates originals also inserted by upload.
- No domain/API/schema/dependency/provider-adapter change. Existing server-side
  file validation, CSRF, storage limits and private photo authorization remain.

## 0.40.1 — Keep background Chat reads within current intent

- Cancel initial saved-note selection when the user changes the draft/action or
  conversation; a dismissed selection cannot restart on request/session refresh.
- Refresh usage independently after a saved request so slow metadata cannot keep
  Chat busy. Discard obsolete counts/errors after new requests, navigation or
  unmount while retaining the saved result and safe write retry behavior.
- Serialize conversation paging, deduplicate appended IDs and scope late list
  errors to the current conversation. New conversations remain available during
  background list reads. Cancel obsolete pages during context/session changes.
- No domain/API, migration, dependency or provider behavior change.

## 0.40.0 — Read a saved private photo in Chat

- Choose **Read a saved photo** in Chat, deliberately load/select from the private
  five-item paged library, and explicitly read the original with the configured AI
  connection/model. Keep transcription evidence and the unverified single-item
  proposal in the selected persistent conversation. Selection makes no AI request.
- Preserve unsent text drafts, existing consent/connection/model/budget gates and
  human review before inventory. Freeze exact request arguments after uncertain
  responses, retain pending turns for safe checks, and clear photo choices/read
  results on conversation intent changes, including a new unsaved conversation.
- A completed request whose usage refresh fails remains visibly saved; it does
  not become an uncertain request or invite another model call. Uploads stay in
  Photos; multi-item photo receipts and arbitrary photo questions remain separate.
- Reuse existing private photo/chat domain services. No migration, dependency,
  provider-adapter or public request-schema change; no live provider call/redeploy.
- Let narrow Chat grid tracks shrink and wrap provider action buttons; browser
  verification shows no page overflow at 390px with the photo picker active.

## 0.39.0 — Compare complete bounded current records

- Explicitly compare two private item records in Assets: current statement versions
  and evidence, incoming/outgoing relationships, aliases, gallery links, discovery
  units, receipt claims and unique cross-source purchase evidence. Preserve source,
  status, dates, exact integer display and whole-line/order amount scope.
- Flag differing statements over overlapping/unknown dates, replacement links,
  distinct receipt units and competing current order/receipt totals. These are
  inspection warnings; no identity decision or merge is performed.
- Use one read snapshot across collections and the shared receipt reader. Refuse
  partial comparisons when a collection or 30,000-byte response cap is exceeded;
  expose section counts/limits and historical-source labels. Read-only HTTP/MCP
  share the same owner validation. UI clears obsolete reads on close/navigation.
- Historical versions remain in original record views. No schema migration,
  dependency, provider request, database write or production redeploy.
- Fix an existing photo-upload grid minimum width that caused horizontal asset-page
  overflow; browser inspection confirms the comparison stacks at 390px width.

## 0.38.1 — Preserve correction chronology

- Record evidence batch move/restore explanations and audit events at or after
  every changed decision and both participating item records, even when the
  system clock stalls or moves backward. Historical reads at the correction's
  timestamp now include its effects; reversal remains a later recorded action.
- Individual reassociation and undo share one transaction timestamp for their
  explanation, decision and audit instead of sampling separate clocks.
- Preserve existing episodes, replay results and snapshots. No retrospective
  timestamp rewrite, schema migration, dependency or provider change.

## 0.38.0 — Requested and scheduled Gmail purchase discovery

- Container publishing now confirms the active GitHub token's `write:packages`
  scope before verification/build and rechecks account/scope before upload. Missing
  scope gives the refresh command immediately; package-specific write access remains
  required. Preserve prompt-free publishing explicitly selected by `-Publish`.

- Opt into AI discovery in Scans or daily/weekly schedules using your private
  OpenAI, Claude or Gemini connection. Evidence-only scans remain available.
- Validate exact quotes, quantities and labelled order/line identities before
  deterministic inferred inventory writes; reuse canonical purchased units across
  messages. Weak matches, shipments and cancellations require existing Review.
- Cache completed extraction, including empty results, atomically with evidence,
  decisions and scan checkpoints. Recheck consent, credential revision, lease,
  cancellation and source corrections before committing. Reuse the daily AI budget.
- Result counts link to evidence, review and asset correction. Migration
  `0021_email_discovery` adds the private cache; no existing record rewrite.
  Inline email text only; attachments, monetary extraction and live verification
  remain outside this release. See [usage and limits](docs/EMAIL_DISCOVERY.md).

## 0.37.0 — Reviewed cross-source purchase evidence

- Purchases connects saved order, receipt, shipment and payment evidence to the
  existing retailer/account/order identity. Reuse canonical purchases already used
  by item reconciliation; attaching evidence never creates physical items or
  ownership facts. A payment cannot create a new purchase or establish contents.
- Source quotes, exact currency amounts and optional event dates remain separate
  claims, never summed into balances. Conflicting current order totals are shown;
  historical/deleted-source claims remain visible but are excluded from comparison.
- Correct, move, withdraw and deliberately reattach source associations with immutable
  history, optimistic heads, owner checks and stable request retry. Private HTTP/MCP
  and paged source/evidence/history UI; product chat stays read-only.
- Migration `0020_purchase_evidence` adds owned source-association revisions without
  replacing existing purchases, receipts or line details. One current association
  per source and 50 current sources per purchase. Automatic email extraction,
  financial allocations, refunds and full record consolidation remain later work.

## 0.36.0 — Private modular daily and weekly scans

- Create, edit, pause and resume private Gmail scan schedules in Scans. Choose
  local time, IANA timezone, weekday, lookback window, search and message limit;
  inspect next-run time and the last run's evidence/progress.
- Generic calendar scheduling dispatches the same registered source handlers and
  durable run queue as manual scans. Enqueue and due advancement are atomic;
  downtime produces one latest catch-up, overlaps are recorded as skipped, and
  changed/disconnected local mailbox grants block scheduling until explicit resume.
- Migration `0019_scan_schedules` adds owned schedule metadata. First-party tzdata
  supports Windows/Linux timezone calculations; spring gaps advance to the first
  valid minute and repeated autumn times run once. Five schedules per user with
  existing scan caps. No new AI/asset creation or mail-arrival trigger.
- Publish a meaningful early plan commit/push for new feature branches, preserving
  verification and the final commit/push/PR/merge/cleanup workflow.

## 0.35.0 — Modular requested email evidence scans

- Request bounded Gmail text imports in Scans, inspect progress and results, cancel
  pending work and browse original/corrected email evidence in Memories. No AI
  request or inventory creation occurs during import; attachments are omitted.
- Server-registered typed handlers share durable SQLite runs, owner authorization,
  atomic evidence/checkpoint commits, bounded recovery and replay protection.
  Gmail credentials stay encrypted; scan APIs and read-only MCP reveal no tokens.
- Migration `0018_modular_scans` preserves existing data and adds scan runs/results.
  Scans resume after restart; connection changes stop old work. Daily/weekly
  recurrence is the next increment. Live Gmail access remains unverified.

## 0.34.0 — Separate private Gmail consent

- Connect an individual Gmail mailbox through a separate read-only Google OAuth flow in Settings. Use PKCE and hashed one-time state bound to account/session/browser; refresh credentials remain in the encrypted vault and never appear in responses.
- List/disconnect only owned mailboxes; reconnect preserves mailbox identity and protects new grants from stale disconnects. Existing vault removal disables the mailbox. Fixed bounded Google endpoints; no mail mutation, automatic scan or AI request.
- Migration `0017_private_mailboxes` adds owned mailboxes and expiring consent flows plus a credential owner index. Document the additional Gmail API/scope/callback setup. Live Gmail access remains unverified. This is the prerequisite for modular manual and scheduled scans.

## 0.33.1 — Keep Chat evidence with the current conversation

- Ignore late citation pages and errors after closing evidence, selecting another
  conversation, starting a new conversation or unmounting Chat. Old completion
  cannot clear a newer citation read's loading state.
- Clear old receipt/asset review panels when changing conversations, and prevent
  opening citations from a conversation while its messages are loading. Preserve
  conversation drafts, completed turns, existing review/write and retry behavior.
- No domain API, schema migration, dependency or provider change.

## 0.33.0 — Link existing private photos into item galleries

- Deliberately load and choose a saved private photo from a paged gallery, then
  link the same original into another physical item without uploading its bytes
  again. Preserve other galleries, receipt mappings, ownership and claim evidence.
- Private HTTP/MCP enforce owner, physical-item and expected-version checks.
  Repeated existing links do not duplicate writes; stale retries cannot recreate
  a later removed link, and deleted originals cannot be linked.
- Keep uncertain-response retry identities and recover from gallery reload
  failure without repeating a saved link. Coordinate gallery controls during
  linking. New attachment audit events retain both photo and item IDs.
- Ignore old gallery pages after a refresh and old transcription reads after
  selection changes or closing evidence. Preserve new uploads when initial
  metadata arrives late; stale errors cannot replace the current photo view.
- No schema migration, dependency, model call or change to original deletion.

## 0.32.1 — Recall current corrections and incoming history

- Include up to three own/incoming corrections and canonical inferred inventory
  membership when recalling a named asset, independent of keyword matches. Retain
  the existing two-record/eight-source/24 KiB context limits and citation checks.
- Discover incoming correction sources by either linked item; a later move from
  the same origin to another target no longer hides an earlier incoming action.
- Attach current-versus-superseded ownership/replacement and association-version
  metadata to named, keyword, HTTP and MCP source reads. Show historical-state
  labels in evidence inspection; preserve original text and event dates.
- Answer instructions distinguish moved evidence and withdrawn statements from
  current claims. No additional provider call, schema migration or dependency.

## 0.32.0 — Record sourced replacement relationships

- Explicitly choose an existing physical item that replaced another item, record
  an explanation and optional known event date, and inspect the resulting stated
  graph relationship from both private item histories.
- Preserve distinct records, receipt units, exact purchase claims and ownership
  states. A replacement never implies a sale, a verified event or merged identity.
- Withdraw the latest unchanged replacement statement with a sourced explanation;
  preserve original episodes and temporal history. Safe retries and transaction
  rollback apply to both operations through private HTTP/MCP and the UI.
- No schema migration, dependency or live-provider change.

## 0.31.0 — Review and reverse discovery-evidence batches

- Preview all 1–5 current discovery associations before explicitly moving them
  to one existing physical item. Preserve other receipt units, exact original
  sources, typed purchase claims and the earlier decision history. Refuse the
  entire operation if the preview changes or two receipt units would collide.
- Reverse an unchanged batch with one explained action; stale item corrections
  or changed associations prevent reversal. Exact retries remain idempotent,
  including after snapshot recovery. Private HTTP and MCP share the same service.
- Notes, photos, aliases, manual facts and relationships stay on their original
  records. This is evidence movement, not whole-record consolidation. Preview
  passages are bounded excerpts with source links; browse history uses summaries.
- No schema migration, dependency or live-provider change.

## 0.30.2 — Recover from failed correction-form reloads

- Catch manual item-reload failures and show a retryable message while preserving
  the correction draft. Prevent edits or writes during that reload, clear the
  error after successful retry, and keep completed-write retry behavior unchanged.
- Reloading never submits a correction. No domain/API, migration or dependency change.

## 0.30.1 — Keep asset navigation stable during slow requests

- Ignore old reload and correction-completion callbacks after the user selects
  another item. A late response cannot reopen the previous record.
- Guard asset-list and correction-history pagination against graph navigation,
  selection changes and unmounts. Stale pages, errors and loading completions cannot
  replace the current view or append another item's history.
- Preserve completed corrections and existing safe retry behavior. No backend
  domain/API, migration, dependency or provider changes.

## 0.30.0 — Inspect evidence moves and receiving history

- Show the exact selected decision passage and its source before a correction.
  Distinguish decisions and targets by record ID and unit; compare source/target
  evidence without selecting or merging items. A new search clears old targets.
- Show incoming reassociation explanations in the receiving item's correction
  history with private pagination and original/receiving names in source context.
  Incoming reads preserve each item's independent correction write-version chain.
- Retain actual newly created targets on new correction actions so their receiving
  history is discoverable. Older new-target actions without target metadata are
  unchanged; they remain accessible on the original item's history. No migration,
  dependency, provider call or automatic whole-record consolidation.

## 0.29.1 — Keep current inventory and matching consistent

- Exclude valid negative ownership statements from reconciliation/MCP discovery
  inventory, matching the asset screen. Apply exclusions before pagination; retain
  original bindings and history. An explicit buyback restores current inventory.
- Share current-world ownership predicates across Assets, discovery inventory and
  identity matching. A negative interval blocks automatic enrichment while valid;
  future or ended intervals do not. Start dates are inclusive and end dates exclusive.
- Preserve owner isolation, explicit corrections and evidence. Discovery inventory
  remains limited to discovery-bound assets. No migration, dependency or UI change.

## 0.29.0 — Record clear reviewed receipt identities together

- Add an explicit automatic-identity choice per reviewed receipt line. Fresh
  deterministic identity checks create clear new units or enrich reliable active
  identifiers without asking the user to select a redundant target.
- An ambiguous automatic choice leaves the entire receipt pending with fresh
  candidate comparisons and preserved edited fields. No partial graph writes or
  consumed retry identity. Matching names never identify physical items.
- Preserve selected/excluded lines, explicit purchase/possession, exact source and
  quantity validation, atomic concurrency and safe retries. Cross-line identity
  changes roll back the batch and require manual review. Accepted results label
  automatic decisions. No migration, dependency, provider call or unattended import.

## 0.28.0 — Correct one receipt unit without moving its siblings

- Move one physical unit from a multi-unit source line to an explicitly chosen
  existing item. Other unit targets, ordinals and source history are preserved.
  Purchase details follow current unit associations without dividing line totals.
- Reject duplicate unit targets, missing/foreign targets, stale sibling decisions
  and whole-line undo through this single-item form. Reversal is an explicit
  move back using the current decision; stable retries return their original result.
- Display this item’s unit number in asset history and correction choices. Single-unit
  creation/undo keeps its existing behavior. Atomic owner-scoped HTTP/MCP service;
  no migration, dependency, provider call or general record consolidation.

## 0.27.0 — Compare ambiguous physical items before choosing

- Add read-only candidate inspection to single-item proposals, receipt-line review
  and identity review. Compare two records side by side, including sourced
  manufacturer/model/serial passages, current inventory status and latest corrections.
- Open exact observation/correction evidence without selecting or merging items.
  Page five candidate buttons at a time; load only on request using existing
  authenticated, bounded asset reads. Closed/evicted requests are canceled and late
  responses cannot replace a different comparison. Errors support retry.
- Keep final identity selection explicit and preserve all review/source guards.
  No migration, backend API/tool, dependency, AI call or graph write added.

## 0.26.0 — Record clear reviewed items automatically

- Add a one-action identity decision for reviewed single-item proposals: record a
  clear new item, enrich a unique active serial identity, or leave ambiguity pending
  with its candidate comparison. Similar names never merge physical items.
- Preserve source evidence, explicit reviewed purchase/possession, atomic replay,
  current ownership corrections and conflicting/historical serial review gates.
  Automatic decisions are labeled; manual same/different review stays available.
- Fix single-item PDF proposals accepting evidence after original-file deletion;
  both manual and automatic acceptance now refuse, while rejection/history remain.
  No migration, dependency, provider call, new tool or background ingestion.

## 0.25.0 — Reviewed purchase recall in Chat

- Include up to three currently linked receipt lines per matched asset in bounded
  read-only Chat recall, using the same owner-scoped service as Assets. Preserve
  exact currencies, whole-line quantities, latest revisions and withdrawn unknowns.
- Mark receipt sources so absent/omitted reviewed details cannot be silently
  replaced by older raw totals. Label historical corrected/deleted sources and
  retain citations; never infer unit prices, combine currencies or sum duplicate
  receipt-line appearances across physical units.
- Fix named-record recall that lost photo/PDF provenance unless keyword search
  independently found the same source. Share source labels across both paths.
  No extra provider call, schema change, dependency or write/model tool.

## 0.24.0 — Purchase records on asset details

- Show linked receipt lines, latest currency-preserving totals/dates,
  exact quotes and
  recorded revisions directly on each physical asset. Open original source or the
  receipt editor/history without searching old conversations. Refresh summaries
  after editing; unknown and withdrawn values remain explicit.
- Follow current reconciliation bindings rather than the receipt's original
  acceptance result, so reassignment/dismissal and undo update the correct item.
  Flag corrected/deleted originals as historical sources; preserve source evidence.
- Add bounded, owner-scoped HTTP and read-only MCP receipt-link pagination. Whole
  line totals are never presented as per-unit prices or combined across receipts.
  No migration, dependency, provider call or automatic financial aggregation.


## 0.23.0 — Correct individual photo attachments

- Remove a photo from one asset gallery while preserving its private original, other gallery attachments, transcriptions and claim evidence. Reattach by uploading the same file to that item.
- Add owner-scoped HTTP/MCP correction and gallery action, audited with both photo and asset IDs. Safe retries do not repeat removal; stale actions cannot remove a newly reattached link. No migration or dependency change.

## 0.22.0 — Explicit receipt currencies

- Support printed USD, EUR, GBP, CAD, AUD and JPY line totals in suggestions, review and immutable history. Store exact integer minor units; use whole yen for JPY and two decimals for the others. Never convert currencies or infer them from symbols.
- Migration `0016_receipt_currencies` preserves existing USD history and request replay. Downgrade refuses to discard non-USD claims. Existing API callers default to USD for compatibility.

## 0.21.0 — Source-backed purchase-detail suggestions

- Find uniquely labeled USD line totals and ISO purchase dates in saved receipt sources without an AI request. Copy exact passages into an editable draft only on request; saving still uses owner-scoped validation and immutable revision history.
- Ambiguous, invalid, unsupported or unavailable source values remain unknown. No accounting arithmetic, automatic inventory changes, schema migration or new dependency.
- Add a linked source-version badge at the top of the README and a version consistency test. The badge does not describe an already running container.

## 0.20.0 — Source-backed receipt purchase details

- Add explicit USD line totals and purchase dates to confirmed purchased receipt
  lines without another AI request. Require exact item/total and labeled date
  passages; leave ambiguous values unknown. Store line totals as integer cents,
  once for all units; never infer a unit price or multiply by quantity.
- Keep immutable revisions with source quotes, purchase-world date and recorded
  time. Correct or withdraw claims without erasing history; guard concurrent edits
  and preserve exact retries after a lost response. Source corrections/deleted
  originals block new writes while historical claims remain readable.
- Add private HTTP/MCP reads and writes, paginated history and a receipt editor.
  Migration `0015_receipt_details` adds a constrained typed claim table; no new
  dependency. No automatic financial extraction, accounting totals or redeployment.

## 0.19.0 — Review multiple receipt items and quantities

- Suggest up to eight source-quoted receipt lines from a saved note, reviewed PDF
  text or photo transcription; explicitly select ownership, quantities and new or
  existing physical units before one atomic confirmation. Cap each receipt at 20 units.
- Preserve drafts in Review, exact source provenance and reviewed field values;
  block stale sources, deleted originals, duplicate unit choices and changed matches.
  Retry a lost confirmation safely without duplicate records or partial batches.
- Share the existing consent-gated OpenAI/Claude/Gemini runtime, owner-scoped HTTP
  and MCP services. Migration `0014_receipt_proposals` adds private draft/replay
  storage; no new dependency. Prices, dates and accounting remain deferred.

## 0.18.0 — Browse and capture private memories

- Replace the Memories placeholder with an owner-scoped evidence library: literal
  search, source-type filters, current/earlier note versions and stable newest-first
  pagination. Original source reads, corrections and history reuse shared services.
- Capture exact note text directly without a chat, AI permission or inferred assets;
  preserve request identity through connection loss and repeated/concurrent capture.
- Preserve photo/PDF categories through corrections; expose private library reads
  through typed MCP. No schema migration, provider call or new dependency.
- Fix asset evidence views that discarded photo/PDF provenance and mislabeled
  derived text as an original statement. Use the shared evidence panel, including
  original-file deletion notices and correction history.
- Fix evidence image overflow caused by a heading layout rule affecting all child
  sections; ignore stale source/page responses during navigation and search.


## 0.17.0 — Private PDF evidence and reviewed text

- Upload owner-scoped PDF originals, inspect automatic text extraction and explicitly
  save reviewed text to searchable memory. No automatic asset creation or provider call.
- Preserve original downloads and source links through note corrections and graph
  evidence inspection. Original deletion retains reviewed source history explicitly.
- Bound uploads to 8 MiB / 10 pages, extraction to 4,000 characters, and private PDF
  storage to 200 active files / 256 MiB per user. Use a separate local parser process
  with decompression/time limits and Linux CPU/address-space limits. No inline PDF
  execution or OCR. Migration `0013_private_documents`; add pinned pypdf dependency.

## 0.16.0 — Google Gemini alongside OpenAI and Claude

- Add Google Gemini to private Chat, saved choices and photo reading using an
  owned `google` AI credential. Google sign-in OAuth remains separate.
- Use stateless Gemini Interactions requests with structured output, streaming,
  optional sanitized JPEG input, fixed endpoint and header-only API key. Disable
  provider storage/background work/tools and retain shared consent/usage checks.
- Do not expose thought content. Validate final structure, citations and usage;
  redact failures and reject managed-agent model IDs. Google currently documents
  Antigravity agent without the structured-output/output-token controls required
  by this runtime; its integration remains deferred. No schema or SDK dependency
  change. Live Google access remains unverified (synthetic/mocked tests only).

## 0.15.0 — Recall sourced records and graph connections

- Let the shared chat runtime plan up to two exact record-name lookups, inspect
  current sourced facts and optionally read a bounded one-step neighborhood.
  Same-named physical items remain separate and ambiguous matches stay explicit.
- Preserve source corrections, assertion status, valid dates and original citations.
  Cap records, facts, sources and total context; omit whole facts rather than
  truncating their values. Add graph links for inspected records in replies.
- Expose owner-scoped exact name/alias lookup through private MCP. The app runtime
  uses the same domain services with no model writes, SQL access or extra provider
  planning call. No migration; live-provider access remains unverified.

## 0.14.0 — Streaming evidence-backed replies

- Stream OpenAI and Claude answer text into a marked, transient draft in Chat.
  Validate the completed structure and source citations before saving the reply.
- Drop drafts on failure, cancellation or disconnect; preserve the saved request
  and existing idempotent retry behavior. Bound provider events, output, queue size
  and browser stream parsing; cancel pending work when the stream closes.
- Keep per-call consent, credential/session checks, usage limits and fixed endpoints.
  No schema change. Provider streaming is verified with synthetic mocked events;
  configured live-provider access remains unverified.

## 0.13.0 — Remember private chat model choices

- Explicitly remember or forget an owned AI connection and model from Chat; restore
  that account's choice when reopening Chat. No browser storage or shared defaults.
- Saving a choice never enables external AI, reads a secret or calls a provider.
  Removed credentials clear the effective choice without a provider fallback.
- Migration `0012_chat_preferences` adds an owner-scoped preference table and leaves
  existing conversations, memory, appearance and external-AI consent intact.

## 0.12.0 — Sourced home and vehicle profiles

- Add specifications, VIN/serial/model, filter dimensions, room paint and maintenance
  statements to existing private asset/place records, or explicitly create a distinct
  home/vehicle record. Creating a profile does not assert ownership or parts fitment.
- Preserve exact source statements, stated/inferred/unknown status, optional world-valid
  dates and correction history. Retry-safe atomic writes reuse the memory core.
- Add private profile inspection to MCP, a responsive Profiles view, original evidence
  inspection and graph navigation. No migration or external lookup is required.

## 0.11.0 — Interactive evidence-backed graph

- Explore private records and their stored connections with keyboard-accessible nodes,
  zoom, bounded one/two-step traversal and an alternative record list.
- Inspect fact status, direction, valid dates and original evidence; inferred and unknown
  relationships have distinct line styles. Literal facts remain visible without edges.
- Navigate between graph records and asset details/photos. All graph reads reuse the
  owner-scoped memory service; no model calls, invented connections or schema change.

## 0.10.0 — Per-user light and dark themes

- Select Light, Dark or System in Settings; preserve the choice per user across
  sessions without changing external-AI consent or credential storage.
- Apply semantic cream/sage and dark forest palettes across existing views,
  including chat, assets, photos, review/evidence controls and status banners.
- Migration `0011_appearance` defaults existing preferences to System. Sign-out
  and account changes clear the previous account's appearance; System follows
  device changes without storing private preferences in browser storage.

## 0.9.0 — Claude alongside OpenAI

- Select a private Claude (`anthropic`) or OpenAI connection for evidence-backed
  answers, saved-note proposals and photo reading, with one shared memory store.
- Route by owned credential metadata to fixed provider endpoints; no fallback,
  arbitrary URLs or model write tools. Both providers share consent, daily budget,
  per-call credential checks, cancellation, citation and source validation.
- Add bounded Claude Messages JSON/vision adapter with local strict validation,
  supported wire schema normalization, redacted failures and no retries.
- New live-call result records retain provider/model labels. Switching a connection
  clears the model field. No migration or new runtime dependency; live provider
  access remains unverified (synthetic/mocked verification only).


## 0.8.0 — Persistent review queue

- Add a private paginated Review inbox for pending item proposals and unresolved
  identity matches, with filters, exact evidence and shared Chat review state.
- Resolve same/different items or exclude a discovery with stale-head/candidate
  checks and safe replay. Not sure leaves the record pending; multi-unit linking
  requires a distinct existing item for every unit. Names never auto-merge items.
- Typed authenticated HTTP/MCP adapters reuse existing durable proposal/decision
  records; no migration or model calls are required by this feature.


## 0.7.0 — Private receipt and nameplate photos

- Add authenticated JPEG/PNG/WebP upload, private originals, metadata-free previews,
  per-user byte deduplication, paginated Photos and asset galleries, and downloads.
- Explicit consented vision reading produces an unverified, correctable transcription
  and one reviewed item proposal; attaching a photo never creates assets. Accepted
  proposals link the original photo atomically to their resulting items.
- Enforce 8 MiB / 20 MP / single-frame inputs, two concurrent uploads, 200 photos /
  256 MiB per owner, and existing AI budgets/session/cancellation rules.
- Migration `0010_private_photos` stores deferred binary originals and previews in
  the private SQLite database so operator snapshots restore both bytes and links.
  Deletion clears originals/previews; derived text/history and earlier backups remain.
- Pillow 13.0.0 is pinned; model wire and privacy checks use synthetic providers only.


## 0.6.0 — 2026-10-18

- Add sourced ownership updates (owned, sold, returned, no longer owned),
  single-item confirmation undo and explicit evidence reassociation.
- Keep correction explanations, original evidence, prior decisions and dated
  ownership intervals; reject stale/concurrent conflicting actions.
- Migration 0009 adds private action history without rewriting existing data.

## 0.5.0 — 2026-10-18

- Browse/search private inventory and include historical asset records.
- Inspect sourced item details, inferred ownership, decision/fact history and
  exact original evidence with bounded paging. No schema or data migration.

## 0.4.0 — 2026-10-18

- Propose one physical item from a selected saved note using bounded OpenAI
  extraction; no inventory changes occur until explicit human review.
- Review/edit exact evidence and supported identifiers, check private duplicate
  candidates, and explicitly choose the same or a different physical item.
- Preserve original proposals, human-reviewed fields and source evidence. Reject
  without creating inventory; retry confirmation safely after lost responses.
- Migration `0008_asset_proposals` adds owner-constrained proposal history without
  rewriting existing notes, accounts, sessions, chats, settings or inventory.
- Block stale-note confirmation and duplicate manufacturer-scoped serial creation;
  keep ownership inferred and missing prices/dates unknown. One item per note;
  broader extraction, accepted-asset correction UI and uploads remain later.

## 0.3.0 — 2026-10-18

- Add explicitly enabled, one-click test login with a shared test workspace and
  persistent warning banner. Normal sign-in remains protected and separate.
- Display the application version on the login screen and inside the app, with
  the exact Git revision when embedded by the release process.
- Establish one application version source and verify package/API/container
  metadata agree. Older images retain their original metadata.

This is the initial visible versioning baseline. Source completion does not imply
that the corresponding Docker image has been published or deployed.
