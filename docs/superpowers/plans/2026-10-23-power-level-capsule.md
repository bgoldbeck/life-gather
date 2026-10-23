# Power level capsule

Requested by Lisa on 2026-10-23: condense the Power Center's main power level
panel into a small capsule so the rest of the Power Center gets more room.

## Scope

- Replace the full-width growth panel in the Power Center hero (stage icon,
  stage name, points, wide bar and five-stage ladder) with a compact pill that
  sits in the hero row beside "Check all locally".
- The capsule keeps the same facts: current stage, confirmed points (or the
  confirmed–possible range for an incomplete score), a small meter with the
  same accessible name and value text, and the stale state.
- The next stage and its threshold move into the capsule's accessible
  description and hover title instead of a visible five-stage ladder.
- No backend, API, scoring or migration change. Dock controls are out of scope.

## Acceptance checks

- Power Center component tests still find the `Power level` meter with the
  same value text, and cover the capsule's stage, points and next-stage hint.
- Hero is visibly shorter in light, dark and phone layouts; before/after
  screenshots saved to the project's `power-level-capsule/` folder.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run format:check` pass.
