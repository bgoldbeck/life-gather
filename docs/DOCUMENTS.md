# Private document evidence

From v0.56.0 Documents accepts PDF, Word `.docx`, Excel `.xlsx`, plain text `.txt`,
Markdown `.md` and CSV `.csv`. Every original remains private and downloadable.
Extraction is local and needs no AI connection. Review/correct text before **Save
reviewed text to memory** makes it searchable. This creates no assets, verified
facts or accounting records. [Design](superpowers/specs/2026-10-20-broader-document-support-design.md).

Text/Markdown previews retain line numbers; Markdown is shown as plain text. Word
main-body paragraphs and tables have location labels; headers, drawings, footnotes
and layout may be omitted. No Word page numbers are invented. Excel lists worksheets
and lets you preview a range up to 200 rows/50 columns (default A1:AX200); cells retain
sheet/address and raw stored value/type. Number/date formatting is not applied.
Formulas are never run and cached values are explicitly possibly stale/missing.
CSV previews retain row/column positions and allow delimiter/header selection.

Text defaults to strict UTF-8 with BOM handling; UTF-16 BOMs are recognized. Choose
UTF-16 or Windows-1252 explicitly when needed before upload. CSV delimiter detection
is a suggestion; confirm or change it. **Preview selection** never changes the saved
original or a reviewed source. **Use preview as reviewed text** explicitly replaces
the unsaved text draft; saving remains a separate action.

All types share the 8 MiB file, 4,000 extracted/reviewed character, 200 active file
and 256 MiB per-user limits. Partial text/selected ranges are labelled. OOXML
archives are bounded to 500 entries, 2 MiB per entry and 16 MiB total expansion;
workbooks support up to 10 sheets. Password-protected and macro-enabled files,
legacy `.doc`/`.xls`, PowerPoint, OpenDocument and OCR are unsupported. External
links, connections, embedded programs and document instructions never execute.

Metadata includes validated format/MIME and parser provenance, with no invented
page count for non-PDFs. Downloads are attachments with safe format extensions.
Memory's Reviewed documents filter covers all formats; Reviewed PDF text remains
available. Source inspection, immutable corrections and original deletion retain
the existing evidence/history policy. JSON includes format/extraction metadata;
ZIP and encrypted installation recovery preserve new originals byte-for-byte.
Migration `0025_document_formats` backfills existing rows as PDF without changing
their IDs, bytes or source links; downgrade refuses while non-PDF rows exist.

New format parsers use the Python standard library inside a separate process with
the existing 8-second timeout and Linux 256 MiB/5-second CPU bounds. DTD/entity
declarations, unsafe archive paths, duplicate parts and oversized XML are rejected.
The worker has a minimal environment without application secrets; it is bounded
parsing, not a general operating-system sandbox. See Python's official
[XML security](https://docs.python.org/3.13/library/xml.html#xml-vulnerabilities)
and [ZIP archive documentation](https://docs.python.org/3.13/library/zipfile.html).

## Existing PDF behavior

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
