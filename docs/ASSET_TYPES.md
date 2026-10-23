# Editable asset types

Available in v0.59.0. On **Assets**, use **Manage asset types** to edit the five
defaults (Vehicle, Appliance, Electronics, Furniture, Tools & Equipment), create
a private type, or copy a type. Add/rename/reorder fields, retire/restore fields
or types, and inspect definition history. Existing field IDs must be retained;
retirement preserves definitions and values. Later application seeds never overwrite
saved customizations. New fields are optional and unknown until supplied.

**Add asset → Asset type** selects a form; General item is the default.
Values entered there are saved as the user's statements, with their original form
labels and text. Existing duplicate checks and explicit linking apply; a template
is never a physical identity or an ownership claim. No AI is needed.

Open an asset's **Asset type & custom fields** to assign/change its type, supply
fields or correct a specific statement with exact evidence, unknowns and optional
valid dates (end exclusive). Changing type preserves the asset ID, all prior facts,
evidence and relationships. Old-type values remain inspectable/correctable. Retired
fields accept corrections to existing statements, but no new statements. Definition
labels are current display labels; original labels remain in evidence and revision
snapshots. Separate same-model items stay separate. Consolidated member type
conflicts remain visible and require choosing the particular assignment to correct.

## Authenticated interfaces

All operations use the session's owner, never an owner supplied in arguments.
HTTP writes require CSRF. MCP requires the existing private session/Origin/CSRF
protocol, is a domain interface for authorized clients, and does not grant the
in-product AI arbitrary writing or external-provider permission.

| MCP tool | Operation |
| --- | --- |
| `asset_types_list` | Page defaults/custom types; `include_retired`, optional `cursor` |
| `asset_type_get` | Read current definition by `type_id` |
| `asset_type_history` | Page immutable definitions by `type_id`/`cursor` |
| `asset_type_save` | Create with name/fields/request_id; edit with type_id/expected_revision; preserve existing field IDs |
| `asset_manual_preview`, `asset_manual_save` | Existing explicit creation flow plus type_id/type_revision/type_values |
| `asset_typed_get` | Current assignments and paged sourced fields; entity_id/history/cursor |
| `asset_type_assign` | Explicit type assignment; replaces_id required to change a current assignment |
| `asset_type_field_save` | Supplied field value/text, optional dates/replaces_id, stable request_id |

HTTP equivalents: GET/POST `/api/asset-types`, GET `/{type_id}`, GET
`/{type_id}/history`, GET `/assets/{entity_id}`, POST `/assign`, POST `/fields`.
Manual creation continues through `/api/assets/manual/preview` and `/api/assets/manual`.
Use a fresh request ID for a new action and the same full request for an uncertain
retry. Stale definition revisions are rejected; reload before editing. Copy a
definition by omitting type/revision and field IDs. A field value must appear exactly
in supplied text; null represents unknown with an explanatory statement.

Lists contain up to five definitions and a byte budget; history pages contain two
revisions. Follow next_cursor until null. Typed values are byte-bounded pages with
up to five source references per fact; `more_evidence` points to the existing field
history/source interfaces for complete evidence. MCP transport's existing body and
response limits still apply; use sparse creation values and separate field writes
for large statements. Registry limits: 32 fields per type, 45 saved/custom types
plus unused defaults (at most 50 visible definitions), 500 characters per value.

## Storage and boundaries

Migration `0026_asset_types` adds owner-constrained `asset_types`,
`asset_type_fields`, and `asset_type_revisions`. No existing records or old
name-derived `profile_custom_*` predicates are rewritten. New custom fields use
`profile_template_<stable-id>` assertions; VIN uses the existing standard predicate.
Shared manufacturer/model/serial and purchase evidence keep their existing controls
and validation. Fields are optional descriptive text, not accounting, identity
merging, inferred compatibility or a general form-builder platform.

Starter definitions are deterministic and private per owner. Pure reads do not
create database records. A starter is materialized with its initial revision when
first edited or assigned; JSON/ZIP records format 4 includes all saved definitions,
fields and revisions along with sourced assignments/values. Unused defaults remain
application seed definitions. Encrypted operator recovery includes and validates
the registry; there is still no automatic user archive import or live redeployment.
