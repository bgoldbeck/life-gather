# Drag-to-dock panels

Replace the navigation and assistant **Dock** dropdowns with a modern docking
interaction.

## Scope

- Drag a panel by its header. While dragging, highlighted drop zones show the
  left, right, top and bottom edge of its area; the zone nearest the pointer is
  highlighted and the panel snaps there on release. Escape cancels.
- Small dock buttons in each panel header (one per edge) replace the dropdown,
  so docking still works by keyboard, touch and screen reader.
- Collapsing turns a panel into a thin icon rail on its own edge instead of
  hiding it: navigation keeps icon-only destinations; the assistant keeps an
  expand button.
- Saved layouts keep working: existing `lifegather-navigation-dock:<user>` and
  `lifegather-chat-dock:<user>` preferences load unchanged; navigation gains an
  optional `collapsed` flag.
- Narrow screens (800px or less) keep today's top navigation / bottom assistant
  fallback; dragging is off there.

## Acceptance checks

- Frontend tests cover dock buttons, pointer drag with drop zones and cancel,
  icon-rail collapse, legacy saved layouts and drafts surviving re-docking.
- `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`,
  `npm run format:check` pass in `frontend/`.
