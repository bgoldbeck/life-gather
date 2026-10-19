# Download a private record export

Baseline: clean/fetched main efde2511d968f0d8f74e04ad2ca847bd9e89a04b,
v0.43.0, migration 0021_email_discovery. No other branches/open PRs or overlapping
export implementation. Existing memory_export pages cover seven memory tables;
operator_snapshot is explicitly installation-wide and must never become a user API.

Implement the first user-facing portability slice in Settings: explicit download
of a versioned UTF-8 JSON document from one consistent owner-scoped read snapshot.
Include original source text and all memory facts/evidence/aliases/audit/revisions,
reconciliation purchases/lines/observations/decisions/bindings/candidates, reviewed
asset/receipt proposals and receipt details, purchase evidence, asset-action
history, conversations/turns, photo metadata/links and document metadata/extracted
text. Preserve exact stored IDs, quantities, money, statuses, times and JSON text;
do not collapse history or infer missing values.

Explicit frozen table/column allowlist; never auto-export all columns or tables.
Exclude user identity/login/password/session data, encrypted provider credentials,
OAuth flows, settings, AI extraction caches, scan/schedule runtime configuration,
photo/preview/PDF bytes and search indexes. Metadata is useful for matching original
files, but this download is not a complete backup and has no restore/import action.
Operator database/file/key backups remain separate.

Bound the whole download to 10,000 records and 16 MiB of serialized output. Refuse
overflow without any partial download; release the read transaction on every path.
Do not stage personal data on disk or call a provider. HTTP is a thin authenticated,
CSRF-protected download adapter with fixed safe filename, no-store/nosniff headers
and empty strict request. The domain service owns snapshot, projection and bounds.
No model-writable export tool or browser auto-download on page load.

UI explains included/excluded scope and limits before the explicit button. Show
preparing, success and retryable failure states, prevent duplicate clicks and
abort/ignore late responses after unmount. Release object URLs after download.
Do not depend on credential/vault/AI settings loading to offer data portability.

Acceptance: private empty/nonempty export, original and corrected history, sibling
units, exact JPY/multi-currency/unknown money, photo/PDF metadata without bytes,
chat retained, foreign account and stored credential isolation; schema/field
allowlist, consistent concurrent-write snapshot, record/byte limits and rollback
without writes. Auth/CSRF/no-store/strict input and safe filename. UI no eager
download, explicit scope, uncertain/read failure, session expiry, duplicate-click,
unmount cleanup and keyboard/narrow browser. Full strict verification, synthetic
Linux smoke, v0.44.0 source/GHCR release. No migration/dependency/live call/deploy.
Graphify is unavailable; use actual source/tests and report refresh limitation.
