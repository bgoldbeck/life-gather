# Saved research recall in the asset assistant

> **For agentic workers:** Use superpowers:executing-plans inline, with TDD and one fresh whole-branch reviewer.

**Goal:** Answer later questions about saved product research with inspectable, dated citations.

**Architecture:** Extend the existing model-selected assistant with a read-only `read_asset_research(asset_id)` action over FindingService. Keep research citations separate from memory episode citations. The host supplies citations from actual read results; the model cannot fabricate their metadata or use research as evidence for a write.

**Tech Stack:** Existing Python services, strict Pydantic step schema, React/TypeScript. No dependency or migration.

**Design:** The user authorized continued development against the tracking-first roadmap. This bounded extension reuses the assistant's known-asset IDs, provider consent, read count and context budget. Return at most five findings across a request, active and owner-scoped, with bounded original saved excerpts, dates, title, URL and the existing identity warning. Report truncation explicitly. Source excerpts and generated-answer excerpts remain distinguishable. Never fetch a page or run fresh research. Research does not establish ownership, purchase details or compatibility and never becomes attachment/user evidence for writes. Chat shows saved research citations with an external source link and an asset button, never sending finding IDs to the memory source reader. Historical replies retain their dated snapshot; removal excludes findings from subsequent reads.

## Global constraints

- Baseline: fetched main 47d6dcfdbe68b7ab48aac5ad3d1acb3a30ee3b80, v0.84.1, migration 0035. No open PRs at kickoff.
- Existing physical identity/consolidation and owner isolation must be preserved.
- Existing permission, cancellation, replay, read and 24,000-byte context limits apply.
- Release v0.85.0 only after another remote clash check; no live provider calls or deployment.

## Review focus

- A guessed or foreign asset ID must not reveal a finding.
- Consolidation and reversal must use the current physical identity group.
- Removed findings and repeated reads must not leak or exhaust context with duplicate citations.
- Malicious saved text cannot authorize writes or populate asserted asset fields.
- Generated answer excerpts must never be presented as original source quotations.

### Task 1: Assistant read and host-owned citation contract

**Files:** Modify `backend/src/lifegather/chat/assistant.py`; create `backend/tests/test_assistant_research.py`.

**Interfaces:** Consume FindingService.for_asset(actor, asset_id), existing known-asset ID set. Produce `saved_research` response citations and a read result `{asset_id, items, limited, identity_note}`. Citations include saved metadata and the requested owned asset ID for navigation.

- [ ] Write failing scripted-provider integration tests for recall, dates/excerpt kind/citations, empty/removed/foreign IDs, bounded repeated reads, identity changes and refusal to write researched values.
- [ ] Run focused pytest and confirm failure for missing action/contract.
- [ ] Add the strict action, progress phrase, read dispatcher, bounded projection and host-owned answer citations. Explain provenance and evidence restrictions in the model instruction.
- [ ] Run focused assistant/research suites; expect all pass. Commit the deliverable.

### Task 2: Inspectable citations and release verification

**Files:** Create `frontend/src/SavedResearchCitations.tsx` and its interaction test; modify `frontend/src/ChatPanel.tsx`, relevant docs, version.py and CHANGELOG.md.

**Interfaces:** Consume the Task 1 `saved_research` list; render safe external web links, dates, excerpt provenance and a button using onOpenAsset(asset_id). Keep memory source navigation unchanged.

- [ ] Write failing UI tests for citation metadata, source versus answer excerpts, asset navigation and unsafe URL rejection.
- [ ] Run focused Vitest; expect failure for missing component.
- [ ] Implement the component and wire ChatPanel. Update assistant/research docs, roadmap and v0.85.0 release notes.
- [ ] Run backend full suite, Ruff/strict mypy; frontend full suite, lint/type/build/format and real browser journeys. Expect all pass.
- [ ] Review the whole branch with a fresh read-only reviewer; fix material findings with regression tests, refresh source graph/HTML.
- [ ] Fetch/check overlaps, commit/push/PR, merge exact tested head, clean branches, build/smoke/publish and verify both image tags under the repository's standing release authorization.

## Scope limits

This adds asset-specific recall, not global research indexing, automatic research, full manual downloads, research-based profile writes or provider quality validation. The five most recently saved findings are a bounded selection, not exhaustive search. No personal data or real provider is needed for acceptance tests.

## Review refinements

The host enforces read-only turns after a successful research read, including
asset creation/updates and email scan enqueue. Clarification and limit replies
keep inspected citations. An 8,000-byte UTF-8 budget for the citation list may
reduce the five-finding selection, leaving room for ordinary requests and other
tool results within the existing 24,000-byte runner limit. Six regression cases
reproduce these review findings before the single fix pass.

## Upstream reconciliation

PR125 merged reconnect prompts while this feature was being verified. Reconciled
onto fb84617d1e6e79798e2b93b79f5e3f4dafc8bbda (v0.85.0 / migration0036).
This feature is therefore v0.86.0, with no additional migration. Preserve the
Reconnect button, credential state labels, provider refusal handling and source
citations together. Re-run the full suite and browser checks on this combined
baseline; prior pre-merge test evidence does not cover the new baseline.
