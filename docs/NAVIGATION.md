# Move and resize navigation

Available in v0.57.0. The main navigation starts on the left. Use its **Dock**
selector to move it left, right, top or bottom. Top/bottom positions keep readable
horizontal labels; scroll within navigation when necessary to reach destinations.
All existing pages and the skip-to-content link remain available.

Drag the divider between navigation and the workspace to resize. Or focus **Resize
navigation** and use arrows along its orientation; Home/End choose the current size
limits. Arrow steps are 10 pixels, or 50 while holding Shift. Side width and
horizontal height are remembered separately, with safe viewport-dependent bounds.

Position and dimensions are saved per account in this browser. They are independent
of the contextual assistant's existing preferences; **Reset navigation layout**
returns only navigation to its default left position and dimensions. No messages,
record content or credentials go into layout storage. If storage is unavailable,
the controls still work for the current session.

On screens 800 pixels wide or narrower, compact navigation appears above content.
This does not replace your saved desktop edge or size. A temporarily smaller
viewport clamps dimensions without rewriting them; returning to a larger viewport
restores the saved dimensions. The navigation and assistant occupy separate nested
layout areas, including when both choose the same edge. Changing navigation layout
keeps the current page and unsent assistant draft mounted.

No schema, API, dependency, AI call or live-installation change is needed. This
release implements the navigation section of the [Power Center design](superpowers/specs/2026-10-20-power-center-design.md);
the Power Center capability/health page remains future work. Floating windows and
dragging panels to arbitrary positions are outside this release.
