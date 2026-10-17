# Private user settings and credential vault plan

Requested feature #2: user isolation and credentials. Execute in the main chat only; preserve outstanding edits in the auth requirements and kickoff documents. No Docker rebuild/upload or live integrations.

Implementation verification: 37 backend tests and 11 UI tests pass, plus backend/frontend lint, type, formatting and build checks. Packaged migration/keygen and both Compose variants with the optional vault override were validated without starting Docker. Existing-account migration preservation and local source graph refresh passed. Google OAuth and a production vault key remain installation-owner configuration, not end-user sign-in requirements. The running Docker image was inspected read-only but not rebuilt or restarted.

## Scope and design

Add owner-scoped private settings and a credential vault as the first resources beyond identity. A packaged Alembic revision adds settings and credential tables linked to users. Every service query/mutation takes an authenticated account, and every HTTP adapter derives it from the existing session. No user/owner ID is accepted in request bodies.

Use installed cryptography AES-GCM with a fresh 12-byte random nonce per write and authenticated context binding owner, credential ID, kind, and provider. The installation owner supplies a 32-byte key file outside the database/data and web-static directories. No auto-generation on startup or silent replacement. With no key, login/settings/metadata/removal work but storing/replacing secrets is unavailable. Wrong keys/tampering fail closed. No browser read-secret endpoint; only internal owner-scoped services can decrypt for future integrations. This is encryption at rest, not protection from the machine administrator.

Settings holds an explicit external-AI-processing boolean defaulting false. Credential metadata holds ID, kind (AI/email/bank), provider, user label, and timestamps; no returned secret, suffix, nonce, or ciphertext. Save/replace/revoke in Settings does not contact any provider. Limit to 100 records per user and paginate metadata. Future domain records, files, connector cursors, and jobs must adopt ownership controls when implemented; do not prebuild them now.

## Implementation and verification

1. Write failing service tests for two users, no plaintext persistence, persistence across restart, replacement/revocation, and ciphertext owner/record binding. Implement models, migration, key-loading and credential/settings service with bounded queries and explicit transactions. Add a no-overwrite local key-generation command.
2. Add authenticated private APIs for settings and paginated credential metadata/save/replace/delete. Reuse Origin plus CSRF mutation protection. Test unauthenticated access, guessed cross-owner IDs, forged owner inputs, invalid/large secret bodies without secret echoes, missing key, and separate user preferences. Sanitize validation responses.
3. Add an accessible Settings panel, loading/error states, secret input cleared after submission, replace/remove actions, explicit no-provider-validation copy, and external-processing consent control. No secret in local storage, URL, or logs. Test interactions and errors.
4. Document key generation/mounting/backup/loss behavior and recovery limits. Declare cryptography as a direct dependency. Verify migration upgrade preserves existing sessions; run backend/frontend checks, packaged migration checks, source graph refresh, and commit passing intended work.

## Acceptance limits

Tested resources are identities, settings, and the credential vault. No claims of full isolation for future memory/files/jobs APIs; those do not exist. No real credentials are needed for tests and no external-provider requests are made. Browser-saved metadata is not proof a credential works. Full key-rotation tooling and global session management are deferred; do not replace an in-use key.
