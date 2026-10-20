# Editable asset types implementation plan

Execute in the root chat only; no subagents (user policy).

**Goal:** Add five editable starter types and private custom types to manual asset
entry, with sourced field values and authenticated HTTP/MCP view/add/edit access.

**Architecture:** Owner-scoped type/field registries use stable IDs and immutable
definition revision snapshots. Existing sourced memory assertions store type
assignments and field values, retaining corrections, valid/recorded time and
physical-unit identity rules. Thin adapters share a framework-independent service.
Defaults are deterministic per owner and never create possessions or facts.

**Spec:** ../specs/2026-10-20-custom-asset-types-design.md

## Constraints and review focus

- Preserve existing name-derived profile predicates and all existing APIs.
- Vehicle, Appliance, Electronics, Furniture, Tools & Equipment; generic entry stays.
- Optional text fields only; no inferred values, compatibility or financial strings.
- Stable IDs survive rename/order/retirement. Stale updates conflict; retries replay.
- Owner checks include guessed type/field IDs and export/recovery; no external AI.
- Consolidated items preserve conflicting member assignments and values.
- User explicitly requests MCP read/add/edit for types and typed assets.

## Tasks and acceptance

1. [ ] Write service tests for defaults, custom definitions, revisions, retries,
   stale heads, reserved labels, owner isolation and retirement. Observe failure.
   Implement assets/type_models.py, type_schemas.py, types.py and migration 0026.
2. [ ] Extend manual.py transactionally with selected type/revision and supplied
   fields; preserve identity preview/link/retry guards. Add explicit existing-asset
   assignment and sourced value correction operations. Test atomic rollback,
   same-model units, later optional fields and conflicting consolidation members.
3. [ ] Add HTTP and authenticated MCP tools using the same services; test CSRF,
   authority, bounded results, complete read/create/edit journeys and denied IDs.
4. [ ] Build a small accessible type manager and typed asset detail editor; integrate
   manual selector/dynamic fields. Test interactions, loading/errors and retries.
5. [ ] Export definitions/revisions in records format 4; test private JSON/ZIP,
   migration and operator snapshot/recovery. Document limits and bump to 0.59.0.
6. [ ] Run backend suites/Ruff/strict mypy/build, frontend tests/lint/types/build,
   browser QA and final review. Refresh source graph/HTML once verification passes.
7. [ ] Fetch/reconcile current main, commit/push tested feature, PR/merge/cleanup;
   build isolated Linux amd64 image, smoke, publish SHA/latest and verify digest.

Commit this plan and push early for feature visibility before implementation.
Do not redeploy running instances or enable GitHub Actions.
