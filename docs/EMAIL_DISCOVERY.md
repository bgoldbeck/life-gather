# Gmail purchase discovery

In **Scans**, select **Discover purchases with AI**, choose your private AI
connection and model, then start an email scan. The schedule form has the same
option for daily/weekly discovery. Connecting Gmail alone never runs discovery.
External AI access must be enabled in Settings; OpenAI, Claude and Gemini use the
same extraction/reconciliation contract and the existing twenty-request daily
budget. Your own provider may charge for API usage.

The evidence-only scan remains available. Discovery processes inline text from the
same bounded Gmail importer, including messages previously saved by ordinary scans;
attachments, external links and tracking images are not fetched. Purchase-related
messages may be sent to the selected AI provider. Clear completed receipts with
quoted retailer, explicitly labelled order and stable line/SKU identifiers can
create **inferred**, unconfirmed assets. Quantities require source support. Shipping
messages, cancellations, missing identifiers and possible existing items require
review; ordinary messages create no inventory. This intentionally favors review
over guessing. No prices, dates, warranties or financial allocations are inferred.

Two messages about the same retailer/mailbox/order/line use the same canonical
purchase and purchased units. Name/model similarity alone never merges items. An
existing manually recorded item with weak identity goes to Review. Account scope
comes from the mailbox, never from the model; different mailbox accounts remain
separate until explicitly reconciled. Changing order quantities or conflicting
physical identifiers requires review.

Run results show created/enriched/review counts per message. Reused results are
labelled historical counts, not new writes. Open the original email evidence,
use **Review uncertain matches**, or **Inspect or correct discovered assets** for
the existing same-item, ownership, return/cancellation and undo actions. Corrections
retain history and provenance. Rescanning a corrected source cannot silently apply
the original again; inspect its current revision in Memories/Review instead.

Successful extraction (including no findings), evidence, deterministic decisions
and the checkpoint commit together. Repeating committed work makes no additional
model request or inventory write. A failed or interrupted uncommitted model call
can consume budget again on retry. Already committed messages survive later errors.
Changing AI/mailbox credentials, disabling permission or cancelling stops future
commits; changed scheduled grants pause dispatch until an explicit resume.

Migration `0021_email_discovery` adds a private completed-extraction cache. Original
email episodes and all item decisions stay in the existing evidence/history tables.
Whole-database backups include the cache. No live mailbox/provider calls were used
for implementation verification; provider adapters were exercised with synthetic
responses. Extraction remains fallible and inferred ownership is never verification.
