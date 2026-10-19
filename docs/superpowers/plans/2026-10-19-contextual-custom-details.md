# Contextual assistant: sourced custom details and safe retries

Baseline checked October 19, 2026: clean main 6862f67355219041ef0adcd8fc204179fdb017eb, v0.52.0, migration0023, one checkout, fresh remote branches/open PRs with no overlap. The prior personal archive source passed 568 backend/253 frontend tests, quality/builds, actual browser ZIP and isolated Linux source recovery. Its guarded image publication is running; this early scope commit leaves the active checkout unchanged. Implementation starts after that release and actual-image smoke finish, with another baseline check.

Named custom details work in Profiles and selected-record recall, but deterministic assistant edit grammar still recognizes only eight built-in fields. Add explicit commands such as `Set custom "Tire size" to 205/55R16`, using existing polite prefixes and add/set/update/change/record verbs. Require quoted names to disambiguate separators, preserve exact supplied values and the complete original request as evidence. Narrative quotations, documents and model replies never execute. Missing values ask for an explicit complete command; unstructured follow-up remains VIN-only. Unknowns and valid dates remain in Profiles.

Reuse validated ProfileChange with field=custom/custom_name, existing name normalization/reserved identity fields/48-character ASCII name and 500-character value bounds. Derive the predicate and snapshot lookup from validated data. Map invalid names to safe domain errors so a malformed command cannot leave a pending chat turn. Do not broaden the built-in ProfileField tool contract or introduce model write tools.

Reuse owner-scoped pinned record/version, immutable evidence and corrections, single-current replacement, conflict refusal, exact request replay, atomic domain-write/chat-reply transactions, audit origins, cancellation and consolidated identity. A reproduced existing bug needs the same boundary repaired: after correcting a secondary member's statement through its consolidated identity, a direct organizer/MCP retry compares original subject against canonical ID and refuses. Preserve original subject/provenance and check actual owner-scoped current membership; never authorize another physical item after reversal.

Acceptance: new custom save/correction with both versions and original sources; canonical name variants; exact same-request replay and changed text/name/value refusal; owner/stale/no-context isolation; invalid/reserved/overlong names/values never write; multiple current statements require review; narrative commands never execute. Verify builtin and custom consolidated-member corrections/retries, and changed identity after reversal. Custom writes roll back with reply failure, cancel without writes, and concurrent retries save once. Existing authenticated HTTP and MCP adapters share these services. Browser custom save/correction/source/history and persistence at desktop/390px, concise command help, full appropriate tests/quality/package/frontend builds, graph+HTML refresh and final clash review.

No schema, migration, dependency, provider call, inferred value, privacy-setting change, browser bridge or deployment. Target v0.53.0 if main has not advanced. Keep the current running installation untouched. Complete standing source/PR/merge/cleanup and clean-main image publication/verification. No agents.

Source acceptance: 583 backend /253 frontend tests pass. The initial 13 regressions
failed on baseline; all 15 new cases now pass, including actual HTTP/MCP adapters,
invalid-turn completion, atomic rollback/cancellation/concurrent retry and reversed
identity isolation. Ruff, strict mypy (227 files including smoke), formatting,
wheel contents and frontend production build pass. Browser commands saved CF100,
corrected through normalized cabin-filter to CF200, exposed original request and
both versions, and persisted profile/conversation after reload. At 390px page and
scroll widths are both 390. Isolated Linux mounted-source 42.9 MB recovery preserves
the assistant correction and earlier value. No provider call or live storage.
Final refs/main/open PR/migration checks show no overlap; main remains 6862f67 and
migration remains 0023. Code-only graph/HTML refreshed (3,233 nodes /14,025 edges).
Source and clean-main image release follow acceptance.
