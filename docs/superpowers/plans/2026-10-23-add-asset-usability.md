# Add asset usability

Lisa: "adding assets is weird, clicking the asset type drops the dropdown field
and creates another. Can we review the whole add asset and improve its usability."

## Reproduced

On Assets → Add asset, the type starts as text plus a **Choose asset type**
button. Clicking it removes the button and inserts a separate full-width
**Asset type** dropdown and a help line, which reflows every field below it.
Choosing a type then inserts its detail fields *above* the asset name, so the
name, manufacturer and model jump further down the page.

## Scope

1. Asset type is one real dropdown from the start (catalog loads when the form
   opens). Falls back to General item with a retry if the catalog fails.
2. Order: type and name first, then manufacturer/model/serial, then a
   "<type> details" group, then notes and ownership.
3. Mark required fields, explain the manufacturer rule next to Manufacturer,
   focus the name field when the form opens.
4. Clear heading, consistent field heights, buttons that fit phone width.

No backend, API or schema change. Patch version bump.

## Acceptance checks

- Picking a type keeps the same dropdown in place and only adds a details group
  below the identity fields.
- Saving with a type still sends type_id, type_revision and type_values.
- Light and dark, desktop and phone screenshots before and after in
  /mnt/project-files/add-asset-usability/.
- Frontend lint, typecheck and unit tests pass.
