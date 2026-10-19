# Manual asset entry on Assets

Baseline main 9dfad4f / v0.45.0 / migration 0022. No open PR or overlapping
implementation branch; the private-record-export branch contains its plan only.
Profiles supports manual home/vehicle records but Assets has no manual creation.

Add an explicit Add asset form on Assets: name, optional manufacturer/model/serial
and notes, plus an affirmative current-ownership statement. Save the exact entered
fields as manual evidence and record user-stated ownership, never independent
verification. Leave dates, prices and absent identifiers unknown.

Reuse the existing identity matcher and reconciliation/binding services so later
email/receipt discovery can find the same physical item. Preview possible matches
without writes, then require a fresh candidate snapshot and explicit link/new
choice. Names alone never merge; a reliable serial match blocks duplicate creation.
Refuse silent resurrection of a record with a current non-ownership correction.
Save evidence, decisions, facts and audit attribution atomically and make retries
idempotent. Keep generic HTTP/MCP inputs unable to choose provenance/confidence.

Expose the operation through thin private HTTP and MCP adapters, keeping it out of
the app model write-tool allowlist. Test ownership/CSRF, ambiguity, serial matching,
retry/conflict/rollback, later-source reconciliation and provenance. UI tests cover
form validation, duplicate choices, uncertain retries, errors and cancelled reads.
Keep existing corrections, profile editing and asset details functional.

Target v0.46.0 without schema changes. Commit/push/PR/merge/close after relevant
checks and graph refresh. The user also requested persistent docked chat; implement
that afterward in its own branch/commit/PR. Deliberately release both changes as one
v0.46.0 image after both pass to avoid two uploads on the user's slow connection.
No live model/mailbox calls, Actions, account changes or automatic deployment.
