# Changelog

## 0.3.0 — 2026-10-18

- Add explicitly enabled, one-click test login with a shared test workspace and
  persistent warning banner. Normal sign-in remains protected and separate.
- Display the application version on the login screen and inside the app, with
  the exact Git revision when embedded by the release process.
- Establish one application version source and verify package/API/container
  metadata agree. Older images retain their original metadata.

This is the initial visible versioning baseline. Source completion does not imply
that the corresponding Docker image has been published or deployed.
