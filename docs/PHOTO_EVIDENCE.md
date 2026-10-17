# Photographs, attachments, and graph evidence

User-approved direction, 2026-10-17. Planning only; uploads and graph storage are not implemented yet. Dedicated phone-camera/PWA capture and remote access remain deferred. Ordinary image uploads are part of the first useful release.

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
