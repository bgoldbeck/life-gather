# Load built release images before isolated smoke verification

On a Docker container builder, the release build completed but retained its image only in BuildKit cache. The subsequent pull=never smoke container correctly refused to run an absent local image. Add explicit --load to the existing single-platform Linux amd64 build, preserving its no-push build stage and all authentication/source checks.

Add an offline control-flow assertion that a local build requires --load. Run the publisher/launcher tests and actual local image build plus isolated container smoke. Patch release 0.48.2 updates version/badge/changelog; no domain or schema change. Refresh source graph/HTML, merge the tested patch and verify its clean-main release. Do not enable hosted automation, skip smoke, publish directly from the build or change running containers.

Acceptance evidence: the container-driver fixture reproduced exit 125 without the
fix and passes with it, with all four offline release/launcher test scripts passing.
The 3 backend version tests pass after locked package refresh. A real Linux amd64
build using --load produced a local image; isolated health/UI/auth/defaults,
version/revision, non-root/storage, migration 0023, consolidation, snapshot recovery
and reversal checks passed. That image used the frozen prepatch application tree
3970bdd (v0.48.1); the final v0.48.2 main image remains a separate release step.
Graph/HTML refreshed. No registry upload or existing-installation deployment.
