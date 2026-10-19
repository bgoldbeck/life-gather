# Recovery CLI environment isolation fix

Baseline: main e673e558e1b5eefb78ee9bcccc6786011cfdcaad, v0.50.0, migration 0023. Fresh refs/branches/open PRs checked: no overlap. The v0.50.0 image and actual recovery CLI smoke passed; a separate synthetic probe reproduced this remaining edge case.

A valid recovery bundle cannot be verified when an old environment supplies a Google client ID but its secret was in a now-lost JSON configuration file. Verification/restoration currently construct full operational Settings and fail before opening the bundle. They must not require old login/mail/public-URL settings; backup must still capture and validate actual effective settings.

Scope: isolate verify/restore settings from unrelated operational environment and dotenv values, while preserving configured data/static paths, private staging and served-directory guards. Use current declared application defaults for other fields, disable the old configuration pointer and dotenv reload in this isolated construction, and keep backup unchanged. No schema, dependency, encryption-format or domain-service change. Release patch v0.50.1 unless main advances.

Acceptance: red regression for lost JSON plus partial OAuth environment, partial SMTP dotenv and invalid unrelated public URL; valid bundle verification and fresh restoration succeed, original settings remain unchanged, backup still refuses incomplete operational configuration, private/static path refusal remains enforced. Run affected recovery/config/version tests, lint/format/strict types, wheel validation, code graph+HTML refresh, final source clash check and standing source/release sequence. Rebuild and rerun isolated fresh-image recovery smoke. No provider calls, live data or existing installation restart.

Accepted source fix: four regressions failed before the change and pass afterward.
25 affected recovery/config/version tests, Ruff lint/format, strict typing across
223 source/test/smoke files and wheel build pass. Linux source smoke recovers the
42.9 MB synthetic installation with a partial old OAuth environment and missing
configuration file. The clean v0.50.0 baseline already passed 533 backend and 239
frontend tests plus the guarded image build and actual-image recovery smoke.
Code-only graph and HTML refreshed: 3,133 nodes / 13,641 edges. No application
configuration precedence, bundle format, dependency or migration change. Full
guarded release verification follows the patch merge.
