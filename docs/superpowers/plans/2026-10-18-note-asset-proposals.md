# Saved-note asset proposals

Implement sequentially, without agents. User-approved scope: one saved text note
to one proposed physical item, exact evidence, edit/confirm/reject, possible duplicate
review. Explicit review is the current increment; automatic extraction, quantities,
prices/dates, uploads, general graph correction and an asset dashboard remain later.

Reuse the bounded provider adapter and durable chat turn lifecycle, cancellation,
consent and daily reservations. Extraction sends only the selected current note,
receives strict schema candidates without tools, and cannot write inventory.
One proposal per owned source revision persists even across retries/restarts.
The UI opens extraction from saved evidence and displays a persistent review card.

Migration 0008 stores immutable proposed data and an idempotent terminal review.
Confirm/edit/reject are deterministic typed MCP/HTTP operations sharing one service.
Acceptance atomically commits reconciliation and proposal state; originals and
proposed values remain intact. Identity fields must occur in the exact source quote.
Only purchase/possession can enter inventory; name/model matches require an explicit
same/different decision, reliable identifier matches cannot silently create another
item. Use existing reconciliation ownership semantics (inferred, never verified).
Corrected source versions require a fresh proposal; never revise existing facts.

Verify owner/CSRF/strict inputs, quote/field validation, prompt injection boundaries,
consent/usage/cancellation, failure/redaction, repeated/concurrent acceptance,
duplicate identity, stale source, atomic rollback, paging/export, upgrade and snapshot
restore. Test UI editing, confirmation, rejection, safe rendering and lost-response
retry. Full checks, synthetic browser check, graph refresh if available, then the
standing commit/push/PR/merge/branch cleanup/build/smoke/GHCR publication sequence.

API contract checked against official structured-output documentation:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
