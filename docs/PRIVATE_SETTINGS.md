# Private settings and credentials (feature #2)

Each Google-signed-in account has private settings and credential metadata. Settings can save, replace, and remove API keys/access tokens for future AI, email, and bank integrations. Saving does not validate or connect a provider. Never enter email/banking login passwords. These credentials are not required for Google sign-in.

External AI processing defaults to off per user. Enabling it records permission only; no content is sent by this feature. Future integrations must enforce this preference when executing.

## Installation-owner key setup

Ordinary users never create or enter the server encryption key. Google login works independently. Without a vault key, privacy settings and existing credential metadata/removal work; secret save/replace/decrypt operations are disabled.

Generate a new key once outside the repository and private data volume. Example Windows path, run from `backend`:

```powershell
uv run --locked python -m lifegather.credentials.keygen D:/lifegather-secrets/vault.key
```

This creates 32 random binary bytes without printing the key and refuses to overwrite an existing file. It restricts permissions where supported. On Windows, protect the directory with account ACLs; on Linux, the app UID must be able to read the mounted key. Never generate a replacement over an in-use key.

For source execution, set `LIFEGATHER_VAULT_KEY_FILE` to the path in ignored `backend/.env` and restart. Keys within data/static directories are rejected. An empty setting disables the vault. A configured unreadable/malformed key fails startup; a pinned fingerprint rejects a different key for an existing vault.

For Docker, set `LIFEGATHER_VAULT_KEY_SOURCE` in ignored root `.env` to the absolute host key path. Add the optional override:

```powershell
# Source deployment, using an already built image:
docker compose -f docker-compose.yml -f deploy/compose.vault.yaml up --detach --wait

# Published image, only after an approved update includes this feature:
docker compose -f deploy/compose.image.yaml -f deploy/compose.vault.yaml up --detach --wait
```

The key mounts separately at `/run/secrets/lifegather_vault_key`, outside `/data` and the image. File-backed Compose secrets retain host permission constraints; UID/GID remapping is not guaranteed. On Linux grant read access specifically to container UID 10001, such as ownership 10001 and mode 0400 on a dedicated key file. Do not recursively change shared-directory permissions. Keep the override on later starts. These commands do not authorize an agent to rebuild/upload Docker.

## Isolation and storage

- Migration `0002_private_settings` preserves existing accounts/sessions and adds user settings, owner-scoped credentials, and a server key fingerprint. Migration `0003_memory_core` adds owner-constrained memory tables; file/job tables remain future work.
- AES-256-GCM uses a fresh nonce per secret and authenticates the owner, credential ID, kind, and provider. Copying ciphertext between records/users fails verification. Labels, providers, types, IDs, and timestamps are metadata and remain plaintext in the private database.
- Every credential query/mutation filters by authenticated owner. Foreign and missing IDs both return not-found. Requests cannot select an owner. Lists are paginated and the transactional limit is 100 entries per user.
- HTTP returns metadata only, never secrets, ciphertext, or nonce. Only internal owner-scoped services decrypt; these are not AI tools. Mutations require matching Origin and a session-bound CSRF token. Validation errors never echo submitted secrets. Bodies are capped at 32 KiB and secrets at 8,192 characters.
- The browser clears submitted secrets immediately, even on failure, and does not store them in local storage or URLs. Switching accounts remounts the private workspace. Protect browser/host access; at-rest encryption does not defeat a compromised administrator, machine, or extension.
- Removal deletes the local credential, not the provider token or backup copies. Revoke at the provider separately when needed.

## Backup, loss, and rotation

Back up the key securely and separately from the database. A restored database needs the same key to decrypt; possessing both permits decryption. Lost keys require reauthorizing connections. Do not overwrite the database or clear its fingerprint as an ad hoc recovery action.

Rotation/recovery tooling is not implemented. Restore the original key, or disable vault access to inspect/remove metadata while planning recovery. Never change keys while the server is running.

## Verification scope

Tests cover two-user lists/preferences, guessed-ID writes/decryption, cross-session CSRF, ciphertext storage/binding, wrong keys, save/replace/removal, preservation of existing accounts, and UI secret-clearing/errors. No real credentials or external providers are used. The memory-core service has separate ownership tests for records, search, graph links, and export. Future adapters, files, imports, and jobs require their own ownership tests when introduced.
