# AI asset assistant: first implementation slice

Date: 2026-10-22. Implements the first bounded slice of
[the AI asset assistant design](../specs/2026-10-21-ai-asset-assistant-design.md),
Phase 1 of the [tracking-first feature plan](../../FEATURE_PLAN.md).
Baseline: main `1491494` (v0.59.0, migration `0026_asset_types`), no open PRs or
other remote feature branches.

## Scope

- New `assistant` chat mode using the configured OpenAI, Claude or Gemini
  connection, model and external-AI permission. The local `organize` Assistant
  stays as the clearly labeled offline option and never calls a provider.
- Provider-neutral tool loop (`chat/assistant.py`) over the existing structured
  completion contract. Each step selects one of: search assets, read an asset,
  create an asset, update asset details, ask a clarification, or answer.
- Limits per turn: 6 completions, 8 reads, 1 write action; bounded tool results.
  The account, request ID, readable IDs and versions are host-owned.
- Create: explicit ownership quote, name and manufacturer/model/serial must occur
  in the user's own words; optional profile details in the same request. Possible
  duplicates produce a choice; only a follow-up answer to that saved question may
  confirm a new item or link to a listed existing asset.
- Update: several profile/custom details on one asset in one atomic transaction.
  Values must occur exactly in the user's words; multiple current statements and
  stale record versions produce clarification or refusal.
- The domain write, its sources, and the completed turn commit in one transaction
  after rechecking that the turn is still pending. The reply is a server-generated
  receipt (no model call after a write). Replays return the saved turn.
- Saved clarifications persist typed pending intent in the turn result; only the
  next turn in the same conversation can resolve it, and changed record versions
  invalidate it.
- Frontend: "AI assistant" mode in Chat with the existing provider/model picker,
  Open-asset receipts and choices.

No schema migration is expected (turn result JSON holds pending intent).

## Acceptance checks

1. Scripted provider tests: natural phrasing creates an owned asset with supplied
   identifiers and details; a multi-field update saves all fields with the user's
   exact wording as evidence and preserves corrected history.
2. One invalid or invented value rolls back the whole operation.
3. Missing ownership/value, two same-name assets, duplicate candidates, current
   field conflicts and stale versions ask or refuse without writing.
4. A follow-up answer resolves only its own pending question; "never mind" and
   other conversations do not inherit it.
5. Unknown/foreign IDs, question-only writes, excess steps and second actions are
   refused; another user's records are never read or written.
6. Replay returns the stored result without another provider call or write;
   cancellation before commit prevents the write.
7. HTTP route test and frontend interaction test for the new mode.
8. Backend pytest, mypy, Ruff/format; frontend tests, types, lint, format, build.

Real-provider quality is not verified by these synthetic tests.
