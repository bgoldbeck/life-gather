# Useful Overview page

Requested by Lisa on 2026-10-24: make the Overview page more useful, and make
the hero graphic's icons interactive.

## Scope

- The hero orbit icons become real links: Documents (book), Assets (cubes) and
  Chat (speech bubble), plus the centre leaf for the Graph. Each shows its name
  on hover and keyboard focus, is reachable with Tab and opens its section.
- An "At a glance" row with real counts: assets, documents, photos and saved
  memories (sources). Each tile opens its page. Empty accounts show zeros and a
  first step instead of placeholder numbers.
- "Needs your attention": pending review items and overdue or soon-due
  maintenance, each opening the record. Shows a calm "nothing waiting" line
  when empty.
- "Recently added": the newest assets, documents and photos, opening their
  records. Links to the Timeline page for charts rather than duplicating them.
- New read-only `GET /api/insights/overview` (session required, own records
  only, bounded). No migration, records-format or MCP change.

## Acceptance checks

- Backend: counts and recent items are per-account; secondary (consolidated)
  assets and deleted documents/photos are not counted; review and maintenance
  attention counts match the Review queue and Timeline "coming up" rules;
  401 without a session, 422 for an unknown time zone.
- Frontend: orbit icons have accessible names, show a label on hover/focus and
  navigate; tiles, attention rows and recent rows open their records; loading,
  error and empty states.
- Screenshots in light and dark, desktop and phone.
