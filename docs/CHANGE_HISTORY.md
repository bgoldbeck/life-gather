# Where changes came from

In Profiles, Assets or a selected Graph connection, choose **View … history**.
History is private to the signed-in owner and loads only when requested. Each
field page contains up to five versions; **More field changes** continues it.

Each version preserves the value, stated/inferred/verified/unknown status,
recorded time and known real-world validity dates. An old → new comparison appears
only when an explicit correction links those versions. Multiple independent
statements can remain current, including disagreements.

The origin identifies the server-observed interface and workflow, such as manual
entry, review, correction, import, user statement or AI inference. Known AI
provider/model and scheduled initiation are recorded. A web or MCP request does
not prove a human was present; review does not independently verify its contents.
For reviewed AI suggestions, the original proposal's attribution appears separately
from the later review. Evidence has its own source origin, which can differ from
the workflow that asserted the fact. Open the original evidence to inspect it.

Older events display **Origin not recorded**. Unclassified current operations
display **Origin unspecified**. Neither label guesses who authored a statement.
Retries retain the first successful event's origin. Corrections retain earlier
versions and evidence. Failed transactions create no surviving audit events.

The first slice exposes graph-fact history. Source corrections, item actions,
receipt reviews and evidence moves keep their existing specialised histories.
This is not a universal account activity page or an undo control.

For integrations, authenticated `GET /api/history/fields` and the read-only
`memory_field_history` MCP tool share the same owner checks, cursor rules and
response bounds. Pages accept 1–10 rows; evidence previews show up to three
sources and 400 characters per quote with explicit truncation labels. Responses
over 32 KiB require a smaller page. The app's provider tool allowlist is unchanged.

Migration `0022_change_origins` adds nullable structured provenance to existing
audit rows and a lookup index. Startup migrates automatically; back up the durable
data volume before deployment as usual. No historical origin is backfilled.
