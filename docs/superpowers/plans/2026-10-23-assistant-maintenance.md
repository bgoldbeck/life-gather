# Maintenance Through Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Repository instruction requires sequential root execution without agents.

**Goal:** Create, read and revise one owned asset maintenance task through the existing assistant, with truthful atomic receipts.
**Architecture:** Add a focused AssistantMaintenance adapter to the provider-neutral runner. Expose transaction-sharing MaintenanceService methods so a revision and completed chat receipt commit together. Carry optional validated browser timezone in assistant requests, excluding absent timezone from legacy request fingerprints.
**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLAlchemy/PostgreSQL and React/TypeScript; no new dependencies or schema.
**Spec:** docs/superpowers/specs/2026-10-23-assistant-maintenance-design.md (approved by user).

## Global Constraints
- One existing owned asset and one maintenance write per request; no recurrence, reminders, mileage rules, bulk edits, place expansion or live provider testing.
- Keep existing dates/history/identity, research-read read-only boundary, cancellation, pending origins, provider permission and bounded context contracts.
- Work sequentially in the root chat. Reuse this isolated feature checkout. Standing repository authorization covers tested release delivery.

## Review Focus
- Question/quoted source text must not authorize a task write; exact user quotes and host intent/date validation required.
- Unknown versus unchanged dates must remain distinguishable on revisions.
- Same-name task/asset choices cannot silently select a different physical item.
- Cancellation or receipt failure must roll back task and source as well as chat acknowledgment.
- Clarification follow-ups must keep observed task/asset versions so intervening edits are refused.

### Task 1: atomic maintenance adapter
**Files:** maintenance/service.py; chat/assistant_maintenance.py (new); chat/assistant.py; tests/test_assistant_maintenance.py (new); tests/test_ai_assistant.py fixture schema.
**Interfaces:** create_in(db, actor, MaintenanceCreate) and revise_in(db, actor, MaintenanceChange) return existing acknowledgment. AssistantMaintenance.list(asset_id), read(task_id), write(asset_id, MaintenanceRequest) share runner authorization, stable host request identity, state tokens and atomic receipt.
- [x] Write failing scripted-provider tests for create/completed log, revision preservation, owner/known-ID boundaries, same-name ambiguity, pending/stale observations, injection/research refusal, cancellation/receipt rollback and exact replay.
- [x] Run pytest tests/test_assistant_maintenance.py; confirm unsupported tool/schema failures before implementation.
- [x] Extract transaction-sharing methods without changing public direct-service behavior; implement bounded maintenance tools, host-owned task observations, quoted user intent/value/date validation, and committed-revision receipts.
- [x] Run new tests plus existing maintenance/assistant/research regressions; run Ruff/strict mypy from backend; commit green task.

### Task 2: date context and saved-result UI
**Files:** chat/service.py; chat/runner.py; frontend/src/ChatPanel.tsx; frontend/src/ChatAssistant.test.tsx; backend date/request-key regressions.
**Interfaces:** optional TurnInput.timezone (validated IANA) and request creation timestamp provide stable local today. Missing timezone retains old fingerprints. A saved task receipt supplies existing navigation/sources/changed_entity_id plus a typed maintenance summary.
- [x] Add failing tests for browser timezone transport, missing/invalid zones, relative dates at local midnight, explicit dates and unknown dates, and replay fingerprint compatibility.
- [x] Implement optional context transport and host date interpretation; preserve pending user/date origins across midnight, or ask when the original relative date cannot be established safely.
- [x] Render a host-owned task/date/status summary and existing source/asset navigation; assert refresh notification and exact request retry behavior.
- [x] Run all frontend tests/lint/types/format/build, backend focused regressions and existing eight browser journeys; commit green task.

### Task 3: verification, documentation and release
**Files:** maintenance and assistant docs; roadmap/changelog/version source; local ignored evidence.
- [ ] Fetch and inspect main/branches/PR overlaps, reconcile only missing behavior, choose next unused minor release.
- [ ] Run full backend suite from immutable Linux source snapshot with synthetic PostgreSQL, plus required static/frontend/browser checks. Record baseline and final affected checks separately if upstream advances.
- [ ] Perform whole-branch review sequentially under repository no-agent instruction; reproduce and fix material findings RED to GREEN. Refresh source graph and HTML.
- [ ] Push final source, create/attach PR, verify exact checked head and merge without bypass, clean own merged branches, build/smoke/publish clean-main linux/amd64 image and verify both remote tags. Preserve and report publication failures without claiming success or redeploying the app.