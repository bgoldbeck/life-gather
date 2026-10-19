# Gmail purchase discovery

Approved scope: a separately selected, schedulable Gmail scan which applies bounded
AI extraction to inline email text and reconciles validated physical-item evidence.
The existing evidence-only scan stays available. No attachments, live personal-data
tests, chat write tools, prices, bank matching, or automatic ownership confirmation.

Implementation:
1. Extend the scan checkpoint with an optional transactional handler processor.
   Derived writes, source ingestion, result metadata and the lease checkpoint must
   commit together. Cancellation or changed permissions must prevent derived writes.
2. Reuse Gmail authorization and paging, existing provider adapters, the per-user
   consent switch and daily AI request budget. Freeze the selected credential nonce
   for each run. Cache completed extraction per source, including empty results.
3. Validate exact quotes, item identifiers, explicit quantities and stable order
   identities before deterministic reconciliation. Scope retailer order accounts to
   the mailbox on the server. Only clear purchase receipts with stable line identity
   can create inferred assets; uncertain, shipment and cancellation findings require
   review. Name/model similarity never merges physical items.
4. Expose discovery selection, AI connection/model and outcome counts in Scans and
   schedules. Use the existing evidence inspector, review queue and asset correction
   actions. Keep original provenance and corrections intact.
5. Verify two-user isolation, duplicate messages/orders, quantity conflicts, consent
   revocation, source changes, cancellation, atomic rollback and provider failures;
   run backend/frontend checks and refresh the source graph. Release as v0.38.0.

Operational limits: at most eight lines/twenty units per email and the existing
twenty AI requests/user/UTC-day budget. Provider retries after an interrupted
uncommitted external call can consume another request; committed results are reused.
No LLM tools, SQL, credentials in prompts, remote image fetching or arbitrary URLs.
