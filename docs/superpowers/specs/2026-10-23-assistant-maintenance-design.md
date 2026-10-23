# Maintenance through the built-in assistant

Date: 2026-10-23. Status: approved by user; implementation underway.
Baseline: GitHub main b6d3b6a, application0.88.0, migration0036_credential_auth_state, records format6. Open PR128 changes phone/tablet docks; PR130 adds the Cloudflare staging package. Storage-quota and signup-protection plans are on separate branches. No maintenance-assistant overlap found. Real-provider testing is explicitly deferred by Lisa.

## Intent and approach

Let a person record and manage maintenance in ordinary chat, then inspect the saved task and its evidence/history in existing screens. Extend the provider-neutral AssistantRunner with bounded maintenance tools backed by MaintenanceService. The user selected the proposed feature using existing maintenance records; reusing that service is the recommended implementation choice. A separate command parser would undermine ordinary-language support; a second task model or autonomous scheduler would duplicate existing behavior and expand the request.

## First slice

- Work on one existing, owned asset and at most one maintenance write per request. Use existing selected-asset/search/read and clarification contracts. Place tasks remain available through existing direct UI/MCP.
- List/read current tasks for that asset. Create an open planned task or log completed work directly. Revise a read task to complete, cancel, reopen, or correct user-supplied title/date fields.
- Preserve untouched fields when revising. A title comes from the user's own wording; an existing task title may be retained unchanged. Never infer service intervals, ownership, completion, parts compatibility, prices or mileage.
- Omitted dates stay unknown. Preserve explicitly supplied calendar dates; resolve relative dates only with a trustworthy request date/timezone, otherwise ask. Do not substitute today's date for an omitted completion date. Confirm genuinely ambiguous asset/task/date choices, without an extra approval for a clear supported write.
- The host validates user authorization and values. Model messages, saved task text, files and research are untrusted data. The existing research-read makes the whole turn read-only, including every new maintenance write.
- Reuse owner checks, current-identity resolution, optimistic state tokens and original-source/revision history. Changed tasks or identities refuse stale edits. Stable host-generated request identities make interrupted exact retries acknowledge the original write without duplication or rewinding later history. The implementation must cover the task-write/turn-receipt failure boundary explicitly.
- Return a host-generated saved result, source link and navigation to the existing asset maintenance view; refresh affected record/task displays. Saved outcome must reflect the committed revision, never the model's claim.
- Keep existing completion/read/context limits, cancellation, pending-question expiry, external-AI consent and provider-reconnect handling. Direct maintenance entry continues to work without AI.

## Acceptance and verification

Synthetic scripted providers and real UI interactions cover task creation, logging completed work with unknown/explicit dates, completion/cancel/reopen, unchanged-field preservation, ambiguous same-name assets/tasks, stale task and identity tokens, foreign IDs, unsupported/invented values, untrusted-content injection, research-read write refusal, cancellation, pending answers and retries across uncertain turn outcomes. Verify current/history citations, restored tasks and existing exports remain coherent. Run scoped and required backend/frontend checks from their configured directories; no live provider calls. Refresh the local source graph after verification.

## Boundaries and delivery

No recurrence, reminders, notifications, mileage triggers, automatic maintenance advice, bulk edits, new account settings or schema changes are planned. Continue using the existing Python/React stack and service/MCP contracts. The builder will settle bounded tool schemas, exact date-context transport and transaction/receipt implementation after approval, preserving these requirements. A new minor release is chosen against current main at completion rather than reserving an already-used number. Follow the repository's standing tested-source PR/merge/container delivery rule, with a fresh clash check before merge. Do not redeploy the running installation.