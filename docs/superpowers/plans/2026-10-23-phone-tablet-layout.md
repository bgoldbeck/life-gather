# Phone and tablet layout check

Status: released in v0.86.1.

Goal: confirm the web UI is usable on phones and tablets, and fix real problems.

Scope:
- Screenshot every main page at phone (390x844), tablet portrait (820x1180) and
  tablet landscape (1180x820), in light and dark themes, against a throwaway
  installation with synthetic data.
- Fix real layout problems only: sideways page scrolling, overlapping or clipped
  controls, dock panels that cannot be used, tap targets that are too small.
- No redesign of desktop layouts.

Acceptance checks:
- No page scrolls sideways at any of the three sizes.
- Navigation and chat dock can be opened, used and closed at each size.
- Frontend unit tests, type check, lint, build, backend tests and browser
  end-to-end checks pass.
