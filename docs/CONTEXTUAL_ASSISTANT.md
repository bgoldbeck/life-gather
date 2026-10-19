# Persistent contextual assistant

The assistant lives in the workspace rather than a separate Chat page. It starts
at the bottom, can dock at any edge, and collapses to a permanent toolbar. On
narrow screens it uses the bottom edge. Layout alone is remembered per account
in this browser; messages and drafts are never put in layout storage. Drafts,
the current conversation and pending requests survive page changes and collapse.

Use the default **Assistant** action for explicit local commands:

- `I want to edit my F150` opens Assets with the matching truck in view. Multiple
  matching physical items produce explicit choices; opening does not edit anything.
- While viewing that truck, `Add a VIN number` asks for the missing value. Reply
  with the exact 17-character identifier, or say `Set VIN to …`.
- Supplied manufacturer, model, serial, paint, filter dimensions, maintenance and
  specification details use the same profile service. A single current statement
  is corrected with preserved history; conflicting statements require review.

These bounded commands need no provider or API key. Other phrasings may require
the shown command form. Choose **Ask AI** for broader questions; its existing
provider, consent and usage requirements still apply. It can read sourced facts
for the selected record, but has no profile write or navigation tools. Original
evidence and model replies never become executable commands.

The context label shows the page and actual server-resolved record. Sending pins
the record ID and version before any network wait. Changes to that record reject
stale writes. Retrying retains the original request and context; profile writes
and the completed chat reply commit together. Loading old history never navigates.
A delayed reply also cannot navigate after the user changes context; its explicit
Open button remains available. Refreshing the browser reloads saved conversations;
unsent drafts are session-only.

External authenticated MCP clients can call `workspace_context_get` with an
explicit page/record, then `workspace_organize` with that context version, exact
user request text and a stable request ID. Calls stay within the authenticated
account. They inherit no browser focus or another client's selection. Navigation
results are instructions for that client's own UI, not a remote browser bridge.
These tools do not expand the app model's read-only tool allowlist.

HTTP uses authenticated `POST /api/chat/context` for reads and the existing
CSRF-protected chat turn endpoint with mode `organize` for explicit actions.
The server owns record names, identity, validation and audit origins. No schema
migration is required. Existing requests with no context keep their fingerprints.
