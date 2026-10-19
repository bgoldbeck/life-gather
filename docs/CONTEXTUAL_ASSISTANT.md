# Persistent contextual assistant

The assistant lives in the workspace rather than a separate Chat page. It starts
on the right, can dock at any edge, and collapses to a permanent toolbar. Drag
the divider between the page and assistant to resize it, or focus the divider
and use arrow keys (Home/End select the size limits). Width and height are saved
separately per account; existing saved dock positions are preserved. On
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
- `Set custom "Tire size" to 205/55R16` records a named custom detail on the selected
  asset or place. Names must be in straight double quotes; case and separators
  normalize just as in Profiles. Add/set/update/change/record and the existing
  polite prefixes are supported. Names retain the 48-character ASCII limit and
  reserved identity-field rules; exact supplied values support up to 500 characters.
  The complete original request remains evidence. A missing value asks for a full
  command; bare follow-up values remain VIN-only. Use Profiles for unknowns, valid
  dates or choosing among multiple current statements. The literal word `unknown`
  in a supplied value is ordinary text, not an automatic unknown-status command.

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
Retries of corrections inherited from a consolidated member retain that original
subject and succeed while it belongs to the selected identity. After reversal,
the request cannot be reused to edit a different physical item.
These tools do not expand the app model's read-only tool allowlist.

HTTP uses authenticated `POST /api/chat/context` for reads and the existing
CSRF-protected chat turn endpoint with mode `organize` for explicit actions.
The server owns record names, identity, validation and audit origins. No schema
migration is required. Existing requests with no context keep their fingerprints.
