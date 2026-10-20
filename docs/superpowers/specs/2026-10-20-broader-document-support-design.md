# Broader document support

User decision: 2026-10-20. Status: implemented in source v0.56.0; operational behavior
and limitations are recorded in [Documents](../../DOCUMENTS.md).
Use the existing private Documents/evidence workflow, extended to support Word,
Excel, plain text, Markdown and CSV. Deliver bounded format increments without
regressing PDF handling, existing sources or original-file downloads.

## Initial formats and useful outcomes

| Format | Target behavior | Source context to preserve |
| --- | --- | --- |
| Word `.docx` | Extract readable paragraphs and tables for review and search. | Heading/paragraph and table identifiers; do not invent stable page numbers from a reflowable document. |
| Excel `.xlsx` | Select and review bounded worksheets/ranges; retain readable tabular structure. | Worksheet names, cell addresses/ranges, headers, raw values and available formula/cached-value distinctions. |
| Plain text `.txt` | Decode supported text with explicit encoding errors and review before saving. | Line numbers and original bytes. |
| Markdown `.md` | Preserve headings, lists and readable tables in extracted text. | Heading/line context; links are data, not fetch instructions. |
| CSV `.csv` | Preview detected delimiter/encoding, allow correction, and review bounded rows/columns. | Header choice, row/column positions and original field text. |

Practical examples: keep a Word home inventory or maintenance guide, search a
reviewed Excel appliance list, preserve a Markdown project note, or review a CSV
export with its original rows. A CSV containing transactions does not itself
implement bank-statement import or create accounting records.

Legacy `.doc`/`.xls`, macro-enabled Office files, PowerPoint, OpenDocument,
password-protected files and OCR are outside this initial target. Reject unsupported
formats clearly; do not claim all Word/Excel files work. Future formats need their
own scoped parser and acceptance checks.

## Shared upload and evidence flow

Choose/upload a supported file, retain the exact private original, inspect the
extraction preview and warnings, select/review content, then explicitly save it
to memory. Preserve the distinction between original bytes, parser output,
human-reviewed text and later inferred assertions. Text review does not independently
verify its contents or establish ownership. No automatic asset/accounting writes.

Retain filename, validated type, size, per-user content hash, parser version,
extraction status and source-location metadata. Repeated uploads remain idempotent
within the owner's workspace; a format or filename match never merges physical assets.
Search and source inspection link reviewed passages to the original and available
locations. Corrections retain provenance and temporal history. Original deletion
must explain which reviewed evidence/history remains, as existing PDF behavior does.

Generalize Documents labels, accepted types, empty/error states, source inspection,
private metadata/tool responses, export manifests and backup/recovery coverage.
Existing PDF IDs, links, reviewed text and history must survive any required migration.
Personal archives must include supported active originals byte-for-byte with correct
type/extension and hashes; restore verification must cover new file types as well.
Do not silently truncate tabular evidence into a misleading complete record.

## Parsing and presentation boundaries

Use format-specific local parsers behind a shared typed service contract. Select
libraries and verify current official APIs during implementation, not in this design.
Keep parsing isolated and bounded by input size, decompressed size, execution time,
memory, document elements and extracted characters. Excel/CSV also need explicit
sheet/row/column/cell limits and selection controls. Report omitted content and
unsupported constructs; refuse safely where meaningful extraction is impossible.

Validate file content as well as extension/MIME. Treat compressed Office containers
as untrusted archives, guarding decompression and path traversal. Never execute
macros, formulas, embedded programs, external links or data connections. Cached
spreadsheet values may be absent/stale; label them and do not recalculate or present
them as verified results. Preserve dates, money, identifiers and leading zeros
without guessing currency, rounding values or silently coercing field text.

Present Markdown and document text safely, without active raw HTML/scripts or
remote-resource fetching. Downloads retain original bytes and remain attachments;
do not execute spreadsheet content during preview or export. Extracted content is
data, never instructions for the server, assistant or coding agent. External model
processing remains separately permissioned and unnecessary for basic local extraction.

## Acceptance for implementation

- Upload each supported format, inspect its preview, review/save text, search it
  later and follow source context to the correct original.
- Word paragraphs/tables and Excel/CSV headers/rows retain useful readable structure;
  selections and truncation are explicit. Formula/cache and encoding ambiguity
  cannot silently become factual data.
- Repeated upload/review is idempotent; user A cannot read or deduplicate against
  user B's metadata, extraction, sources or originals.
- Test malformed, mislabeled, encrypted, oversized and decompression-heavy files,
  parser timeout, unsafe Markdown, external links and formula-bearing workbooks.
- Existing PDFs remain readable/downloadable with unchanged provenance and history.
  Corrections and original deletion preserve documented evidence-retention behavior.
- JSON metadata, ZIP hashes/original bytes and encrypted installation recovery
  preserve every newly supported type and its source relationships.
- Accessible upload/review/error flows work in Light/Dark and narrow layouts.

Implement in separate verified increments, with migrations where schema changes
are necessary. Power Center should report only actually released format support
and actual parser health, not this target list as already unlocked capability.
This design update changes no application version, schema or running installation.
