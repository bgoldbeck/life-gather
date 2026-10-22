# AI assistant: asset types and typed template fields

Date: 2026-10-22. Baseline: main `b67bf13`, v0.60.0, migration `0026_asset_types`.
Scope: the remaining Phase 1 item named in [AI assistant](../../AI_ASSISTANT.md)
limits and the [assistant design](../specs/2026-10-21-ai-asset-assistant-design.md)
R4/R6: let the assistant assign an existing private asset type and save that
type's optional text field values. No schema change or new migration.

## Behavior

- New read tool `list_asset_types` returns the user's current (non-retired) types
  with their current field IDs and names. `read_asset` reports the assigned type
  and its field values by name instead of raw template predicates.
- `create_asset` and `update_asset` accept `asset_type_id` and type-field changes
  (`field: "type_field"` with `type_field_id`). The type must be listed for this
  request, current and named in the user's own words; changing an existing type
  replaces the single current assignment with history.
- Type-field values must appear exactly in the user's words and belong to the
  assigned (or newly assigned) type. The standard VIN template field keeps using
  the existing `vin` detail. Retired types/fields, several current assignments or
  statements, and unknown field IDs are refused.
- Assignment, type fields and standard details commit together with the turn
  receipt, or not at all, through the existing `AssetTypes` transaction-scoped
  internals. History records the `ai assistant` method; receipts link sources.

## Acceptance checks

1. Creating an owned asset with a named type and typed values saves all of them
   with sources; reading it in a later conversation returns them by field name.
2. Updating assigns/changes a type and saves several typed values in one request.
3. An invented type (not in the user's words), a value not in the user's words,
   a field from another type, a retired type, or an unknown type ID saves nothing.
4. A failing typed value rolls back the assignment and every other detail.
5. Another account's type IDs are never usable.
6. Backend pytest, strict mypy, Ruff and format from `backend/`; frontend checks
   are unaffected unless UI changes become necessary.
