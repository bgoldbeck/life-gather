# AI assistant streaming status

Date: 2026-10-22. Phase 1 follow-up from the [assistant design](../specs/2026-10-21-ai-asset-assistant-design.md):
"Intermediate UI states may show checking records or saving, without exposing
private chain-of-thought. A draft/streamed answer cannot claim a write succeeded
before its durable receipt."

## Scope

- Allow the existing private `/api/chat/conversations/{id}/stream` endpoint to run
  `assistant` turns as well as `ask`. Other modes keep the non-streaming endpoint.
- The assistant tool loop emits host-written `status` events at real stage
  boundaries: understanding the request, searching assets, reading a record,
  checking and saving details, preparing a question or answer. Status text is a
  fixed LifeGather phrase; no model output, reasoning or draft reply is streamed.
- The terminal `complete` event still carries the committed turn; only it can
  report a saved outcome. Retry, cancel, replay and context guards are unchanged.
- The Chat panel shows the latest status in its existing live `role="status"`
  region while an assistant request runs.

## Acceptance checks

1. Streaming an assistant request yields ordered status events and one complete
   event whose turn matches the non-streaming result (create, update, question).
2. Status events never contain model-supplied text and never say a save
   happened; refused writes still finish with "nothing was saved".
3. Replaying the same request over the stream returns the stored turn without a
   provider call; cancellation during streaming stops before the write.
4. Ask AI streaming drafts and other modes are unchanged; unsupported modes
   remain rejected by the stream endpoint.
5. Frontend tests: assistant mode uses the stream and shows status text; invalid
   status events are rejected; the saved reply appears only from the turn.
6. Backend pytest, strict mypy, Ruff/format; frontend tests/types/lint/format/build.

No schema change, dependency or provider-contract change. Next minor version.
