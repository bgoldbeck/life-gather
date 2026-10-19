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
