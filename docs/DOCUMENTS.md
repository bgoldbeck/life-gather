# Private PDF evidence

Open Documents, choose a readable unencrypted PDF, and upload it. The app retains
the original privately and extracts selectable text locally. Review or correct the
text before selecting **Save reviewed text to memory**. This makes the reviewed
text searchable; it creates no assets or verified facts and calls no AI provider.
Scanned pages may have no readable text: type a transcription or use page photos.

Download the original to compare layout and content. The app serves it as an
attachment rather than embedding untrusted PDF content in its own origin. Source
inspection in Chat or the graph links back to that original. Saved text supports
the existing immutable note correction history; later edits retain its PDF link.
The original file and automatic extraction are separate from reviewed text.

Limits: 8 MiB per file, 10 pages, 4,000 extracted/reviewed characters, and 200 active
PDFs / 256 MiB per user. Truncation is explicit. Matching hashes are idempotent per
user. PDF text is untrusted evidence, not instructions, and extraction may lose
layout, ordering or content. No OCR is included.

Deleting an original permanently removes its bytes and automatic extraction, but
retains reviewed text and evidence history. The UI requires acknowledgment and a
current revision before deletion. Other users cannot read originals or metadata.
Private MCP exposes bounded metadata/extraction reads without file bytes.

Migration `0013_private_documents` stores originals in the durable SQLite database.
The pinned pypdf parser runs in a separate process with an 8-second wall timeout,
2-MiB stream-decompression limits and external JBIG2 decoding disabled. Linux also
applies a 256-MiB address-space limit and 5-second CPU limit. Windows verification
exercises process timeout and parser limits; Linux resource enforcement is not
executed by the Windows test suite. This is a bounded parser, not a general OS
sandbox. No PDF scripts, links or embedded applications are executed by extraction.

Parser references checked 2026-10-18: [pypdf security limits](https://pypdf.readthedocs.io/en/stable/user/security.html)
and [text extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
Multi-item receipt extraction and typed prices/quantities follow separately.
