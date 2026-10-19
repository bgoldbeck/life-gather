# Await asynchronous scan-result focus in verification

The v0.48.0 release rerun loaded the correct saved Chat scan result but its test asserted focus before React's passive effect completed. Wait for that asynchronous focus assertion instead of weakening it or changing runtime behavior. Preserve the assertion that only reads occur and the exact saved job opens.

Validate the focused ScansPanel test repeatedly and the complete frontend suite, lint, format and TypeScript. Review the small test-only diff, refresh source graph/HTML as applicable, merge the tested head, and restart the release checks on clean current main. No application, schema, dependency or provider behavior is intended to change.

Acceptance: focused 3 Scans tests and all 231 frontend tests passed, as did
TypeScript, oxlint, Prettier, production build and 3 backend version checks after
locked package refresh. Release version is 0.48.1 under the patch-release rule;
there is no runtime behavioral or migration change. The existing focus assertion
is retained inside waitFor, which waits for the passive effect instead of assuming
that rendering the result also proves focus has completed.
