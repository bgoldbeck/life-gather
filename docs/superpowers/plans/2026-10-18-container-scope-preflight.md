# Container publishing permission preflight

User-reported GHCR failure: the active CLI token lacked write:packages. The browser
permission refresh has now succeeded. Before any verification/build for -Publish,
query the authenticated GitHub /user response headers and require write:packages.
Explain gh auth refresh --hostname github.com --scopes write:packages when absent.
Report the active account; use it for Docker login. Scope presence is not a promise
of package-specific write access, and no package permissions/visibility will change.

Preserve the user's newer release-script changes that removed interactive prompts.
Update offline control-flow tests accordingly and cover missing scope, missing scope
header, wrong account visibility, and successful scoped publishing. Never print tokens
or contact a registry in these tests. This script-only fix needs no app image rebuild
of its own; it supports the pending email-discovery release.
