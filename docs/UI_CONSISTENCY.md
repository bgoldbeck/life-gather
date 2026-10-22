# UI consistency

Phase 4 of the [feature plan](FEATURE_PLAN.md) gives the working app one visual
language. This page records the shared conventions so new panels match.

## Conventions

Status: delivered in 0.72.0; second pass in 0.79.0.

- **Form controls.** Text inputs, selects, textareas and file pickers inside a page
  share one height, border, radius, padding and focus ring. Checkbox and radio
  labels sit on one line with their box.
- **Keyboard focus.** Every button, link, disclosure summary and form control shows
  the same visible ring from the theme's `--ring` token when reached by keyboard.
- **Messages.** Error messages (`role="alert"`) read as a tinted callout; status
  messages (`role="status"`) use the muted text color. Loading text stays a status.
- **Fact status.** Stated, inferred, unknown and other statement statuses show as a
  small labelled badge, so stated facts are easy to tell from inferences.
- **Page surfaces.** Scans and Purchases use the same bordered page card as the
  other panels; section headings use one size scale.
- **Rows of actions.** Adjacent buttons and filter controls keep an even gap
  instead of touching; buttons in stacked forms keep their natural width.
- **Assistant panel.** The docked assistant uses the same field, checkbox and
  message styles as pages, so proposal, receipt and note-correction cards match
  the forms they lead to. The compact composer keeps its docked layout.
- **Buttons beside fields.** In an `.action-row` that holds a field, buttons and
  checkbox labels match the field's height so the row lines up (Assets search,
  graph focus controls). An empty `.action-row` takes no space.
- **Asset details.** The detail card is an evenly spaced column; its evidence and
  graph links share one row, and section headings follow the page scale.
- **Narrow screens.** At 390px the top bar keeps room for search, and nothing
  scrolls sideways.

Panel stylesheets set only layout (width, grid placement), never their own
control borders, padding or focus rings.

Use `<FactStatus status={...} />` for a statement's status, the `.action-row`
class for a row of related buttons or filters, and `role="alert"` /
`role="status"` paragraphs for messages; the shared styles in
`frontend/src/consistency.css` do the rest. Avoid per-panel input styling.

Docking and panel layout belong to the drag-to-dock work (v0.71.0) and are not changed here.

## Acceptance checks

Review every navigation page on desktop (1440px) and at 390px in Light, Dark and
Forest dark, populated and empty; tab through each page to see the focus ring;
confirm no page scrolls sideways; rerun the frontend tests, typecheck, lint and
format check.
