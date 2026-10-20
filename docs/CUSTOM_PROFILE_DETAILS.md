# Named custom profile details

In **Profiles**, select an existing asset or place, then choose **Custom detail**
under **Detail type**. Enter a name such as **Tire size** or **Fuel type**, the
exact value, and the original evidence or your statement. The exact value must
appear in that text. Your statement remains a user statement; saving it does not
make it independently verified. No AI provider is needed or contacted.

Choose **Unknown** when you do not know the value and explain that in the evidence.
Optional valid-from/until dates describe when the statement applies; the separate
recorded date tracks when it was saved. End dates are exclusive.

Names support up to 48 characters: letters A–Z, numbers, spaces, underscores and
hyphens. Case and separators normalize, so `Tire size` and `tire-size` refer to the
same field. Values and original evidence support Unicode. Standard names such as
VIN, serial, model and filter dimensions use their existing detail types. Custom
details are descriptive statements and do not become identity-matching identifiers.
There is no shared field registry or template designer in this increment.

The planned [editable asset types](superpowers/specs/2026-10-20-custom-asset-types-design.md)
extend manual entry with editable starter templates and private custom types.
They must preserve these existing sourced details and their history; this page
describes the currently delivered per-record workflow.

Use **Correct tire size** (or the matching field name) to choose a saved current
statement to correct. Its name stays locked, the exact previous statement is
superseded, and its evidence and history remain available. Add a separate detail
when recording a different field. Multiple current statements are preserved;
adding a statement does not silently replace another one. **Include correction
history** and **View tire size history** expose the earlier versions and evidence.

Names display readably in Profiles, Assets, Graph, record comparison and field
history. A selected record's assistant context includes its custom details under
the existing private recall rules. The [contextual assistant](CONTEXTUAL_ASSISTANT.md)
also accepts `Set custom "Tire size" to 205/55R16` while viewing an item. A single
current statement is corrected with history; conflicting statements require review.
Use Profiles for explicit unknowns, valid dates or choosing one conflicting version.

Custom statements follow explicitly consolidated identities while retaining the
original record for correction history. Distinct records and purchased units are
not combined by a shared custom value. Personal record downloads and encrypted
operator recovery preserve these ordinary immutable facts without a format change.

## Integration contract

Existing built-in `ProfileChange` payloads remain valid. The authenticated,
CSRF-protected `POST /api/profiles/facts` also accepts `field: "custom"` and
`custom_name: "Tire size"`, together with the existing value/status, source text,
operation key and optional valid dates/replaced-fact ID. Supplying a custom name
with a built-in type is rejected. Custom predicates are stored as
`profile_custom_tire_size`; reserved names cannot impersonate built-in predicates.
Correction must preserve the original predicate and subject, and replay uses the
same existing operation-key guarantees. Reads, paged field history and the
read-only `profile_get` MCP tool share the existing owner checks. No new model
write tool, schema or dependency is introduced. Migration remains 0023.
