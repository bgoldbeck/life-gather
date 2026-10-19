# Named custom sourced profile details

Baseline checked October19,2026: main674d5c8626a11c74a5a4e79334b0d7a0a99c89c1, v0.50.1, migration0023. Clean single checkout, current remote branches and open PRs checked: no competing implementation. Previous release passed537backend/239frontend and fresh Linux recovery smoke. This is the early scope commit, before implementation.

Profiles currently hardcodes eight detail types in both the service and form. Useful details such as tire size or fuel type must be buried in a generic Specification statement. Existing immutable profile facts already support original evidence, confidence/unknowns, valid-world dates, recorded history, canonical consolidation, private recall and portability.

Implement the smallest additional slice: choose Custom detail and supply a meaningful name, exact value or explicit unknown, original evidence and optional valid dates. Normalize bounded ASCII names (48 characters, letters/numbers/spaces/underscores/hyphens) into a separate profile_custom_<name> predicate. Unicode values/evidence remain supported. Reject reserved built-in names and kind/profile_kind rather than letting custom fields masquerade as identity fields. Keep existing ProfileField builtins for bounded chat editing; no new AI write tool.

Use the existing ProfileChange/transaction/history services. Old payloads remain valid. Explicit custom-name validation, stable replay/conflict behavior and corrections preserving the exact original subject/predicate are required. Correcting a custom detail locks its name in the form. Render readable custom labels in Profiles, field history, Assets and Graph without exposing storage prefixes. Do not make arbitrary non-profile graph predicates editable.

No new schema, dependency, field registry/template designer, automatic identity decision, provider lookup, maintenance scheduling or financial inference. Generic fact export, history and recovery retain the meaningful names and original bytes without a format bump. Target v0.51.0 unless main advances.

Acceptance: two-owner service and authenticated HTTP/CSRF boundaries; builtin compatibility; normalization/reserved/invalid name handling; exact source, unknown/date semantics, replay/conflict/atomicity and correction identity; consolidated shared reads, distinct physical units, field history, selected-record recall and export/recovery. Test meaningful UI create/unknown/correction/error-retry interactions and stale navigation behavior. Verify real synthetic browser save/evidence/history on desktop and390px dark/light. No live records/providers. Run appropriate full tests/types/lint/format and builds, refresh code graph/HTML, repeat source clash checks and complete standing source/container release sequence. No agents.

## Source acceptance

552 backend / 244 frontend tests pass, with strict source/test/smoke typing,
lint/format and wheel/frontend builds. Browser checks save a synthetic tire size,
inspect original evidence, correct it with the name locked, retain both versions
in field history, and preserve the record across navigation. Light appearance and
390px dark appearance pass; an explicitly unknown custom fuel type saves through
the real form. Page width390 and main client/scroll width375 show no page overflow.
The temporary tab and server were closed and viewport override reset afterward.

The isolated no-network/non-root/read-only Linux source smoke also preserves the
new custom fact through encrypted backup, verification and restoration with a
42.9 MB synthetic database. Source graph/HTML refreshed: 3,163 nodes /13,737 edges;
AssetsPanel remains partially extracted by the AST tool while TypeScript passes.
No migration, dependency, format, live provider or running-installation change.
