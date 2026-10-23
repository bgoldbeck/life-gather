# Pick saved photos in Chat

Status: in progress on `claude/chat-saved-photo-picker`.

Since v0.69.0 the AI assistant can read one saved photo attached with **Attach a
photo**, but picking is clumsy: the library only loads after a second click,
five large tiles fill a phone screen, the chosen photo shows only as a file name,
and a sent message never shows which photo it was about.

## Scope

1. **Attach a photo** opens the saved library straight away (no extra Load click).
2. Compact square thumbnails in Chat (both the assistant attachment and **Read a
   saved photo**), twelve per page, file names on one line; no page overflow at
   390px.
3. The attached photo shows as a thumbnail chip before sending.
4. An AI assistant reply records which photo or document the user attached, and
   the user's message shows it (thumbnail for photos), also after reload. Stored
   in the turn's existing result JSON: no migration.

Out of scope: searching photos by name, attaching several files, attaching from
the Photos page.

## Acceptance checks

- Frontend unit tests for auto-load, thumbnail chip and the sent-message chip.
- Backend test that an assistant turn with an attached photo records
  `attachment` (kind, id, name) and a carried-over follow-up does not.
- Full backend suite on PostgreSQL, frontend lint/typecheck/tests/build.
- Screenshots at 1366px and 390px, light and dark.
