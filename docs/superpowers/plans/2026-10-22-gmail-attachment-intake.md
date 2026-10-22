# Gmail attachment intake (Phase 2, feature 3)

Bounded, private intake of supported Gmail attachments as reviewable original
documents. Requested now by the user, ahead of the plan's "after the text loop is
reliable" gate, so limits stay conservative.

## Scope

- New registered scan source `gmail_attachments` ("Import Gmail attachments"),
  reusing the read-only Gmail connection, mailbox revision checks, 31-day past
  window, one-active-scan and daily run limits.
- Only attachments whose filename has a supported document extension (PDF, DOCX,
  XLSX, CSV, TXT, MD) are fetched; at most 4 MiB each and three per message, at
  most 20 messages per scan. Inline images, other types and larger files are
  listed as skipped, never downloaded.
- Each fetched file goes through the existing document upload (local extraction,
  SHA-256 dedupe, per-user quota, private file storage). No AI reads it; its text
  becomes evidence only after the user reviews it in Documents, as today.
- The email's header/text is saved as the provenance source (same namespace as the
  evidence-only import, so both scans share one episode), and a new
  `email_attachments` link table records message, part and document.
- The assistant can queue this scan with purpose `import_attachments`.

## Acceptance checks

- Supported attachment is stored once in file storage and appears as a document
  linked to its email; replaying the scan creates no duplicate document or link.
- Oversized, unsupported or inline parts are skipped without being fetched.
- Another user's scans/documents are unaffected; mailbox disconnect stops the scan.
- Migration upgrades/downgrades; backend tests, ruff and strict mypy pass.
