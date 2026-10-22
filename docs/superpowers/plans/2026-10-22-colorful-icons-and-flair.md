# Colorful icons and visual flair

Date: 2026-10-22. Phase 4 (UI beautification) slice requested by the user:
"spruce up the UI ... icons for things like email, bank, etc. ... the power bar,
the bright colors ... make it feel alive ... everything should have color and
icons, if it's relevant ... make sure the color differences don't get too
chaotic, stay on theme." References: `.references/lifegather-standard-dark-theme.png`,
`.references/lifegather-earthy-dark-theme.png`, `.references/admincn-dark-dashboard.png`.

## Scope

- A small, fixed set of category accent tokens (`--tone-*`) defined per theme so
  each area of the app has one recognisable color: email, finance/purchases,
  documents, photos, assets, maintenance, AI, graph, review, power, settings.
  Tiles use a soft tint of the tone with the full tone on the glyph, so color
  stays accent-only and surfaces keep the active theme.
- Distinct, meaningful icons for every navigation destination, shown in colored
  tiles; the current page glows in its own tone.
- Power Center: a forest-scene hero banner and a contextual "growth" power bar
  (Seedling → Sprout → Growing → Thriving → Flourishing) derived from the
  existing capability score, colored stat tiles, category icons on source cards
  and color-coded status pills (ready, needs attention, needs setup, unverified).
- Overview feature cards use the same category tones.
- No behavior, API, data, schema or dependency change; scores and statuses are
  only restyled, never invented.

## Acceptance checks

1. Every navigation item has a distinct icon in a colored tile, legible in light
   and dark appearance, with the current page clearly marked.
2. Power Center shows the forest banner and power bar reflecting the real score
   (or an explicit incomplete/stale state), with colored source and status cues.
3. Colors come from one shared token set and stay consistent with each theme.
4. Frontend tests, typecheck, lint, format check and build pass.
