# Read a saved private photo in the current Chat

Baseline: clean GitHub main `3098b40`, v0.39.0, migration head
`0021_email_discovery`. No competing branches/PRs at kickoff.

Expose the existing authenticated `extract_photo` turn in Chat through an explicit
five-item paged private-photo chooser. Loading/selecting metadata must never invoke
AI, upload/copy bytes or create assets. The user selects an existing provider/model
and explicitly submits a read; existing consent, budget, owner validation and
single-item proposal review remain authoritative. Explain that the selected
original goes to that provider and the result remains unverified.

Keep the read and source/proposal links in the chosen persistent conversation.
Preserve unsent text drafts when switching to/from the photo action. Freeze the
chosen photo/provider/model after uncertain responses; exact request replay and
pending-turn status must not become a new model call. Clear the photo choice on
conversation changes and discard stale chooser responses on close/navigation.
Use fixed explanatory request text: the existing photo extractor does not accept
arbitrary photo questions. Multi-item photo receipts and new uploads stay outside
this increment; Photos remains the upload/gallery interface.

Acceptance: deliberate selection/no eager reads, paging/errors, stale read guards,
consent/connection/model/budget gates, exact body/retry after lost response,
pending-to-complete recovery without duplicate IDs, preserved drafts and new/other
conversation reset, original evidence/proposal links and provider failure handling.
Verify the existing private backend path with synthetic providers, full backend/
frontend checks, browser and Linux smoke; no live AI/email. No schema/dependency or
provider-adapter changes. Release v0.40.0 through the standing source/GHCR workflow.

Verified: 411 backend / 159 frontend tests, Ruff lint/format, strict mypy,
Prettier, oxlint, TypeScript, Vite and package builds pass. Fourteen new UI cases
cover explicit no-eager selection, source links, preserved drafts, connection/
model/consent/budget gates, exact lost/pending retries, usage-refresh failure,
paging/errors and late success/error after new/existing conversation changes.
The initial action tests and new-unsaved-conversation race tests failed before
their implementations. One composed private backend test proves prior messages
remain, duplicate photo reads reuse one provider/budget request, sources remain
private and inventory stays empty until review.

Synthetic browser verified a labelled photo, saved conversation, source image and
unverified single-item proposal. Narrow 390px QA exposed an existing Chat grid/
button-row minimum width; minmax tracks and wrapping now keep document width at
375px with no overflow. Viewport reset, preview tab/server closed. Linux-compatible
smoke checks the same domain lifecycle and snapshot replay. Graphify unavailable;
source graph/HTML refresh could not run. No live provider calls or migration.
