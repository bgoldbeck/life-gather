# UI layout polish: borders and spacing

Date: 2026-10-22. Phase 4 (UI beautification) slice requested by the user:
"some parts of the UI don't have a clear defining border and lots of dead space."
References: `.references/admincn-dark-dashboard.png`,
`.references/lifegather-ui-concepts.png`, `.references/lifegather-power-center.png`.

## Scope

- Structure, spacing and separation only. Panels and sections sit on clearly
  bordered card surfaces, consistent radii and padding, tighter vertical rhythm,
  and less empty space in the shell (sidebar, topbar, main content).
- Theme-agnostic: reuse existing tokens (`--border`, `--card`, `--muted`, …).
  No palette or token value changes; a parallel thread owns theme colors.
- No behavior, API, data or schema changes.

## Acceptance checks

1. Major workspace panels render as bordered surfaces distinct from the page
   background in both light and dark appearance.
2. The shell wastes less vertical/horizontal space at desktop widths and stays
   usable at 800px and below.
3. Frontend tests, typecheck, lint, format check and build pass.
