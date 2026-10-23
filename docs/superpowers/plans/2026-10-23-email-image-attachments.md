# Email image attachments and scheduled attachment scans

Status: released as v0.96.0.

## Problem

Gmail attachment intake (v0.77.0) saves only document files. Photos of
receipts, nameplates and items that arrive as JPEG/PNG/WebP attachments are
listed on the saved email text but never stored, and attachment scans can only
be started by hand or from Chat, not on a schedule.

## Scope

1. `gmail_attachments` also downloads JPEG, PNG and WebP attachments (at most
   8 MiB each, the photo upload limit) and saves them through the normal photo
   upload: format/dimension checks, metadata-stripped preview, SHA-256 dedupe,
   the 200-photo/256 MiB photo limit and the per-account storage quota. Other
   limits stay: three attachments per message, 20 messages per run. No AI
   provider sees the image and no asset is created or attached.
2. Migration `0039_email_photo_attachments` lets an `email_attachments` link
   point at a photo instead of a document (exactly one of the two).
3. `GET /api/photos/{id}/email-sources` lists the linking emails; Photos
   shows **Open the email this photo came from**, like Documents.
4. Scans → Scheduled scans can schedule attachment imports (daily/weekly,
   at most 20 messages), using the existing schedule runner.

## Acceptance checks

- Simulated Gmail run saves one document and one photo, links both to the
  email source, replays idempotently, and keeps other accounts isolated.
- An undecodable image or full quota is listed as not imported; the run
  completes.
- A schedule for `gmail_attachments` dispatches a bounded attachment scan.
- Frontend tests cover the schedule type choice and photo email link.
