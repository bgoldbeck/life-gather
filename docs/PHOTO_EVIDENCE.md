# Photographs, attachments, and graph evidence

## Multi-item receipt photos (v0.42.0)

In Chat, choose **Review a receipt photo**, explicitly select or upload an original,
then select **Review receipt photo**. The configured provider reads an untrusted
image into an unverified transcription and up to eight item lines/twenty total
units. Inspect every quoted passage and quantity against the original through
**View receipt source** before reviewing purchase/possession and confirming lines.
Only the existing receipt review changes inventory; each unit remains distinct.
Photo links follow accepted lines. Prices, dates and financial allocation are not
inferred; optional source-backed purchase details retain their existing review.

The first transcription and receipt draft save in one transaction. Invalid quotes,
unsupported quantities, serial/quantity conflicts, non-mention ownership or excess
limits leave neither a draft nor a new transcription. Unreadable input can retain
the source with no item suggestions. Omitted/uncertain lines remain for inspection;
the bounded reading is not a claim to have captured an entire long receipt.

An existing receipt review is reopened without another AI request. If a single
reading already exists, resolve its active proposal first; the receipt action then
uses the current saved transcription rather than overwriting it or retransmitting
the image. Correct that text in the existing note workflow if needed. All photo
reads still require an owned, retained original. A source correction invalidates
stale review; original text, versions and earlier decisions remain available.

The saved-photo single-item action and Photos reading can reopen a receipt review
already associated with that photo. Lost/pending Chat responses retain the same
mode, photo ID and request identity for retry. Uploading/selecting alone makes no
model call. Cancellation or deletion before persistence discards the model result.

Receipt validation also refuses a cropped quote that hides an explicit multiple
on its source line. Repeated short passages are checked against all matching line
contexts (at most 32 before requiring a less ambiguous quote). Use a full exact
item/quantity passage rather than defaulting such a line to one unit. Existing
accepted history is preserved. Since v0.69.0 the AI assistant answers questions
about an attached photo ([details](AI_ASSISTANT.md#photos-and-documents)).

## Direct Chat upload (v0.41.0)

Choose **Read a saved photo** in Chat, then choose a file under **Or upload a new
photo** and select **Save photo privately**. Accept JPEG/PNG/WebP up to 8 MiB;
the existing server also enforces image dimensions, single-frame decoding, private
storage quotas and filename validation. Choose a general photo, receipt or
nameplate purpose. Saving selects the original in the current Chat but creates no
conversation, AI request, gallery attachment or inventory item. It works without
external-AI permission. Use **Read selected photo** separately when ready; existing
permission, connection/model, budget and human-review requirements still apply.

Originals remain in Photos if you change the action, start another conversation or
leave Chat. The upload does not send an unsaved text draft to a provider. A lost or
server-error response freezes the original file/purpose for **Retry same photo
upload**. The existing private content hash reuses an active original rather than
creating a duplicate. You can inspect Photos after leaving an uncertain upload;
leaving does not cancel or delete a server-side save. Client callbacks after leaving
the picker are ignored. A new original also remains available in the saved picker;
appended library pages deduplicate it. No schema, API or provider-adapter change.

## Saved-photo reading in Chat (v0.40.0)

Choose **Read a saved photo** in Chat, load the private twelve-item paged library,
select one original and explicitly submit **Read selected photo**. This uses the
selected persistent conversation and existing provider/model, consent and daily
budget controls. Loading/choosing a thumbnail makes no AI call; submitting sends
the selected original to that provider. Existing saved readings are reused.

Transcription remains unverified and at most one identifiable item is proposed.
Inspect the source and review the proposal before inventory changes. Other chat
messages and an unsent text draft are not sent to the photo extractor; switching
back to text preserves that draft. Arbitrary photo questions and multi-item photo
receipts are not supported by this single-item action; use the separate receipt
photo action above. Uploads are available in Chat as of
v0.41.0, as well as in Photos.

Uncertain responses retain the exact request and freeze the choice for safe retry.
A still-pending turn can be checked again without generating a new request ID.
Conversation changes clear the selection and discard late chooser responses.
A completed request stays saved if refreshing daily usage fails. No new schema,
provider adapter, credential scope or deletion behavior is introduced.

User-approved direction, 2026-10-17. The v0.7.0 initial photo slice is implemented; broader graph/event linking remains planned. Dedicated phone-camera/PWA capture and remote access remain deferred. Ordinary image uploads are part of the first useful release.

## User experience

Users can upload photographs in chat or attach them to an existing item's detail view. A car can have appearance/condition images, VIN/nameplate images, repair/damage photos, and photographed receipts. Selecting the car in the graph opens its detail panel with a Photos & Documents gallery. Selecting a sourced fact opens its specific supporting image, with a relevant crop/highlight when available.

Users can say, "Attach these photos to my car." Resolve an existing item first; ask if multiple cars match. Attaching images must not automatically create another car. A photo without a clear target can remain unattached or await review. Users can add/edit captions and select attachment purposes without an AI provider.

Keep the graph readable: gallery images need not all become visible nodes by default. Document/source nodes can be expanded or filtered when exploring evidence. A photo may link to multiple relevant entities or events without duplicating file storage.

## Attachment versus evidence

An attachment means a user associated a photo with a record. It does not establish every visible fact. A claim-evidence link records what the image supports: for example a legible VIN label may support a VIN, while a body photo may document appearance or damage. Ownership, exact model, purchase date, and warranty do not become confirmed merely from an attachment.

Store the original upload as provenance and keep OCR, annotations, crops, and thumbnails as derived material. Extraction results are candidates with uncertainty; do not overwrite the image when correcting text or a link. Separate upload time, user-stated event time, and any camera metadata date; a capture timestamp does not automatically prove when an event occurred.

## Storage, identity, and permissions

- Save private files outside the web static root on durable storage, with owner-scoped database metadata and opaque file IDs. Do not accept filesystem paths from the browser.
- Originals, thumbnails, download/view responses, OCR text, and gallery/graph queries require the same authenticated owner checks. Do not create public image URLs or share caches between users. No sharing feature is implied.
- Hash original bytes and reuse identical files only within that user's workspace. Repeated attachments to the same target are idempotent; one file can support several distinct links. Different images/crops do not prove different assets, and matching bytes do not establish physical identity.
- Validate supported image types, actual decoding, dimensions and byte limits during the upload implementation. Do not rely on filename extensions. Browser previews should use safe derived images; do not expose embedded metadata such as location by default. Preserve original evidence privately, with explicit user download and deletion behavior.
- Send images/OCR to external models only under the user's configured permission. Ordinary attachment and viewing must work without model access. Images and extracted content are data, not instructions to tools.
- Distinguish removing a link from permanently deleting a file. Link removal leaves other valid links intact. File deletion must explain affected evidence, remove original/derived copies according to policy, and avoid leaving facts falsely presented as still supported. State backup-retention limits. History preservation does not override explicit privacy deletion.
- Backup and restoration must cover database records and original files consistently. Derived previews may be regenerated; source originals cannot be reconstructed from OCR.

## Acceptance criteria

1. Attach car photos to an existing car, inspect its gallery from the graph, and open the original evidence for an extracted VIN without creating a second vehicle.
2. Re-upload identical bytes and repeat the same attachment without duplicate files/links. Link one file to both a repair event and its asset.
3. A general car picture remains an attachment unless particular assertions are supported. Uncertain OCR/model matches remain visibly uncertain and correctable.
4. User B cannot list, fetch, download, link, or delete user A's originals or derivatives, including guessed IDs or traversal attempts. Identical uploads by different users do not disclose each other's files.
5. Restart and restore preserve sources and links. Link removal, source deletion, and derived-preview regeneration follow documented semantics.
6. Uploading/viewing/captioning works without external AI permission; extraction never bypasses that setting.

Implement this with the planned evidence core and upload stages, with their own migrations and tests. Google OAuth live setup and private-user foundations precede personal photo ingestion.

## Implemented initial slice (0.7.0)

Use Photos or an asset's Photos & Documents gallery to upload a single JPEG, PNG,
or WebP, up to 8 MiB / 20 megapixels / 10,000 pixels per side. Animated images,
invalid decodes, compressed request bodies and unknown formats are rejected. The
server limits active uploads to two and each owner to 200 photos / 256 MiB of
original-plus-preview data. Same bytes reuse an owner's active photo and asset
link; separate owners receive independent records. Display filenames never become
filesystem paths. Decoded, oriented previews are fresh JPEG canvases capped at
2048 pixels and 2 MiB, without inherited EXIF/GPS/comments. Originals retain their
exact bytes (including metadata) and download only as attachments with canonical
extensions, octet-stream and nosniff. All image routes require the private session
and no-store; mutations require origin and CSRF checks.

From v0.66.0 originals and previews live in private [file storage](FILE_STORAGE.md)
(`/data/files` by default, or a private S3-compatible bucket), outside the webroot;
the database keeps their keys, sizes and hashes. Operator recovery bundles still
include all image bytes, metadata and attachment links. Metadata list/MCP reads never load image BLOBs.
Use the authenticated original download for per-file export. Exporting only graph
JSON does not export image bytes.

Read photo with AI explicitly sends only the selected sanitized preview to the
configured vision-capable model, after the existing external-AI preference check.
It uses the same persistent chat turns, selected private credential, request replay,
usage limit and session/cancel checks. The model has no tools. Strict bounded
transcription and candidate schemas plus exact quote/identifier validation gate
persistence. Source and proposal commit together. Empty/ambiguous readings create
no inventory. The transcription remains AI-generated and unverified, with original
photo provenance through every note correction. A saved reading is reused; corrected
notes can be proposed through Chat. A person must explicitly state purchase or
possession, check duplicates and confirm before any inventory write. Acceptance
atomically links the original to resulting assets. Uploads/general attachments alone
support no ownership claim. Models may misread text; human review is required.

Delete photo is a separate acknowledged operation that clears the original and
preview for all attached assets. A changed attachment/reading/claim invalidates a
stale deletion acknowledgment. Derived text, facts, metadata and audit history are
retained and marked through the deleted-photo provenance; unresolved proposals from
a deleted original cannot be accepted. Earlier backups and database recovery pages
may retain bytes: this is not a secure-erasure promise. Reupload after deletion
creates a new record without reviving old links. Link removal, event galleries,
PDFs, multi-item receipts, prices, dates, quantities, chat file picking and graph
navigation are deferred beyond this slice.

Wire references verified for this release: [OpenAI Responses image inputs](https://developers.openai.com/api/docs/guides/images-vision?api-mode=responses)
and [Pillow image API](https://pillow.readthedocs.io/en/stable/reference/Image.html).
No live provider calls or personal images were used in verification.

## Implemented gallery correction (v0.23.0)

An asset gallery offers **Remove photo from this item** separately from deleting
the original. This removes only that photo/asset attachment; the private photo
library, original bytes, other asset galleries, transcriptions and source-backed
facts remain. A gallery attachment is not a claim-level evidence link. Correct a
claim separately through its source/fact workflow if its evidence is mistaken.

The transaction records an immutable `photo_detached` audit entry with both IDs.
HTTP and MCP derive the owner from the session; the expected photo version blocks
stale removal after reattachment. Retrying an already absent link is harmless.
Upload the same original into the item gallery to reattach it with per-user byte
deduplication. This adds no tables or external requests.


## Link an existing private original (v0.33.0)

In an item gallery, open **Use a photo already saved**, load the private library,
choose a thumbnail/filename/record ID, and explicitly link it to this item. Load
five records at a time; nothing is fetched until requested. The same retained
original and metadata-free preview serve every gallery. Other links, transcriptions,
receipt-unit mappings, typed prices and ownership facts do not change. General
attachment is not claim evidence or ownership verification, and no model is called.

`POST /api/photos/attach` and MCP `photo_attach` use the existing owner-scoped
service with `photo_id`, `asset_id`, and `expected_updated_at`. HTTP writes need
CSRF. A new link requires the current photo version; an already present link is
a harmless retry without another mutation. If a later removal or original deletion
occurred, a stale request cannot restore it. Refetch and explicitly select the
current photo before a new attachment. Safe retries return current metadata rather
than a historical fixed payload. New `photo_attached` audit entries include both
IDs, matching link-removal audit scope; older entries are preserved as recorded.

The chooser keeps an uncertain write frozen for an identical retry. After a
confirmed write, a failed gallery reload offers only a read retry. Other photo
mutation controls are disabled during linking. No tables, dependency, external
request or original-deletion policy change. Chat attachment picking and event
photo galleries remain separate roadmap work.
