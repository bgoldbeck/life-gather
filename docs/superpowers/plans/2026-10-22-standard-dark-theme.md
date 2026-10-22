# Standard dark theme

Date: 2026-10-22. Phase 4 UI follow-up using the user's
`.references/lifegather-standard-dark-theme.png` reference: deep blue/slate
surfaces, teal/cyan accents, bright text and clear status hierarchy.

## Scope

- Rename the existing green dark palette to **Forest dark** (stored as
  `forest-dark`). An Alembic migration moves every saved `dark` choice to
  `forest-dark`, so nobody's current look changes; downgrade maps it back.
- Add the new **Dark** (standard) palette under the existing `dark` value. It is
  also what System uses when the device prefers dark.
- Settings offers System, Light, Dark and Forest dark. Both dark palettes keep the
  `dark` class for Tailwind's dark variant; Forest dark adds a `forest` class.

## Acceptance checks

1. The API, service and database constraint accept `forest-dark`; unknown values
   are still refused.
2. Migrating a database with a saved `dark` theme yields `forest-dark`.
3. Choosing Forest dark applies `dark` and `forest`; Dark applies only `dark`;
   signing out clears both.
4. Text, focus and status colors in the new palette meet WCAG AA contrast.
