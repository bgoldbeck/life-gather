# Upload a private photo directly in Chat

Baseline: clean main cfc0f9d, v0.40.1; fetched GitHub, no competing branches/PRs.
Reuse the authenticated, CSRF-protected bounded photo upload service. Add an
explicit file upload within the existing Chat photo picker; keep AI reading a
separate user submit with current consent/model/usage gates. Preserve text drafts.
Accept JPEG/PNG/WebP up to 8 MiB with server validation still authoritative.
After success select the saved original without an eager AI call or list reload.
Keep uncertain upload retries on the same original file/purpose; content-hash
reuse must not create duplicate originals. Explain that uploaded originals remain
in Photos when leaving Chat. Ignore late completion/errors after context changes.
Cover validation, CSRF/body/name, explicit submit, retry, privacy and unmount;
run full checks, synthetic browser/Linux verification, and release v0.41.0 through
the standing PR/merge/branch cleanup and GHCR rule. No schema/dependency/provider
adapter change, live provider call or running installation deployment.

Verified: 412 backend / 181 frontend tests pass; Ruff lint/format, strict mypy
across src and tests, Prettier, oxlint, TypeScript and package/frontend builds pass.
Fourteen new frontend cases cover explicit upload, validation, request body/CSRF,
uncertain file/purpose retry, rejected files, late context success/failure, no AI
permission, current conversation/draft preservation and paged-library duplication.
One new backend case verifies authenticated upload, CSRF refusal, active-byte
reuse, private access, separate owners and no AI/conversation/inventory effects;
the existing composed photo test now begins with actual HTTP upload before reading.
Strict test checking found and fixed one existing Literal annotation in the
comparison fixture; all twenty affected comparison cases pass without behavior change.
Synthetic browser verified upload selection at unchanged zero usage, explicit fake
vision into the selected conversation, unverified proposal and 390px layout without
horizontal overflow. Linux smoke verifies upload transport plus photo reading,
exact replay, private access, unchanged inventory and snapshot recovery. Graphify
is unavailable locally, so graph/HTML refresh could not run. No live calls/redeploy.
