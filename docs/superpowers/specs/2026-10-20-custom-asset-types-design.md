# Editable asset types and manual entry

User decisions: 2026-10-20. Implemented as the optional-text-field slice in v0.59.0;
see [Asset types](../../ASSET_TYPES.md) for delivered controls, APIs and limits.
This extends the personal-discovery design and manual inventory workflow.

## Purpose

Users can create their own private asset types, select them when manually adding
assets, and modify their types later, including adding fields. Provide useful
editable starter types rather than requiring every user to design a form first.
Type definitions are templates; installing them never creates possessions or facts.

## Starter types

Provide these five common types by default for every account:

| Type | Suggested additional fields |
| --- | --- |
| Vehicle | Year, VIN, odometer with units, fuel/power type, tire size |
| Appliance | Appliance category, dimensions, power requirements, filter specification |
| Electronics | Device category, capacity/storage, connectors, power requirements |
| Furniture | Dimensions, material, finish/color |
| Tools & Equipment | Tool category, power source, battery specification, consumable specification |

All types reuse common sourced name/manufacturer/model/serial, ownership,
purchase-evidence and photo/document workflows where applicable. The table lists
field suggestions, not inferred values or a promise of specialized processing.
Unknowns remain blank/explicitly unknown. Units must be stated. Specs do not prove
parts/battery/consumable compatibility. Purchase money remains in existing exact
typed accounting structures, never template strings or model arithmetic.

## Manual addition and customization

- **Add asset** offers a type selector containing defaults and the user's custom
  types. Selecting **Vehicle** presents its form; an **Add vehicle** shortcut may
  preselect it. Keep generic/manual entry available when no template fits.
- Allow users to create a type from scratch or copy a starter, name/describe it,
  and add, rename, arrange or retire descriptive fields. Editing a starter's
  account-specific definition is allowed; it must not change another user's type.
- The first increment can reuse existing sourced custom descriptive details.
  Richer typed widgets/validation require a separately scoped implementation plan;
  do not prebuild a general form-builder platform or a plugin runtime.
- Example: select Vehicle, enter one explicitly stated vehicle, then later add
  **Winter tire size** to the Vehicle type. Existing vehicles gain an optional empty field;
  new vehicle forms include it. No value is copied, invented or silently backfilled.
- Fields added after records exist default optional. New required-field rules
  cannot invalidate old records or prevent reading/correcting unrelated details.
  If supported later, changes requiring existing-data migration need a preview,
  explicit scope and validation before applying.

## Stable identity, history and isolation

Asset types and template fields have stable owner-scoped IDs independent of display
names. A field rename preserves its values and evidence. Keep type-definition
revisions/audit history separate from asset assertions and their valid/recorded
times. Do not silently relabel historical values or reinterpret their data types.
Retire referenced fields/types from new-entry choices rather than destroy their
definitions, values, provenance or ability to inspect existing records.

Shared system identity fields (VIN, serial, manufacturer/model), physical-unit
reconciliation, evidence, ownership and exact-money rules retain their validated
semantics. Custom labels cannot impersonate them. A custom type is not a new graph
entity kind, product model, ownership assertion or physical-identity merge rule.
Changing a record's type is explicit and preserves its ID, old facts, sources and
relationships; incompatible fields remain inspectable rather than being deleted.

All definitions, field values, forms, selector/search results and background work
are isolated by authenticated owner. System starter seeds may be shared application
code; user customizations and custom types are private. Later seed changes must
not overwrite a user's modifications. Reuse the validated domain services through
thin HTTP/MCP adapters and keep manual creation/correction usable without AI.

## Acceptance for implementation

1. A fresh account sees the five starter types and a generic entry path, with no
   fabricated assets, facts or personal examples.
2. Create a custom type, add fields and select it in manual asset entry. Save
   supplied values with evidence and recall/open the same physical item later.
3. Add a field to Vehicle after records exist; earlier values/history remain intact
   and the new field is optional/unknown until supplied. New Vehicle forms use it.
4. Rename or retire a field/type without losing existing data or evidence. Changes
   preserve stable IDs and have attributable definition history.
5. Distinct same-model units stay distinct; type/name/field similarity cannot merge
   items, infer ownership or convert unsupported specifications into compatibility.
6. Another user cannot list, select, inspect, mutate or export private definitions
   or values, including guessed IDs and same display labels.
7. Export/archive and operator recovery preserve definitions, revisions and links;
   retries remain idempotent. Plan required schema migrations and backwards
   compatibility before implementation; existing name-derived custom predicates
   must not be wholesale renamed or silently discarded.

The original design-only commit changed no application behavior. The implementation
release uses migration 0026 and records format 4; richer typed widgets and required
field migrations remain separately scoped. No running-app deployment is implied.
