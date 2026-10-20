# Encrypted operator backup and recovery

Available in source v0.50.0. These local operator commands recover an entire
installation: **every user's** records, original photo/document bytes, conversations,
authentication/session state, processing jobs and schedules, private credentials,
installation settings and configured vault key. Personal JSON downloads remain
separate and cannot be restored with this command. There is no HTTP/MCP/AI tool
for installation recovery.

From v0.50.1, verification and restoration ignore old Google/SMTP/public-URL and
other operational settings, including a missing JSON configuration file. They
retain environment/dotenv data and static paths for staging and privacy checks.
Backup still requires the actual installation's complete valid configuration.

## Create and check a backup

Run inside the installation's existing container so its configured data directory,
environment and vault-key mount are available. Replace the example container name;
choose a new output filename each time:

```sh
docker exec -it lifegather python -m lifegather.recovery backup /data/installation.lgbackup
docker exec -it lifegather python -m lifegather.recovery verify /data/installation.lgbackup
docker cp lifegather:/data/installation.lgbackup ./installation.lgbackup
```

The prompt hides the passphrase; backup asks for confirmation. Use a strong unique
passphrase of 12–1024 UTF-8 bytes and keep it separately. Losing it prevents
recovery. For controlled noninteractive use, supply `--passphrase-file` pointing
to a private UTF-8 file containing one line (optional trailing newline). There is
no passphrase argument or environment variable. Protect and remove that file
according to your backup procedure; never put its contents in logs or source.

Native Python installations use the same module from their configured environment.
Backup also accepts explicit `--data-dir` and `--configuration-file` overrides.
It captures the effective known application settings, including Google/SMTP
secrets, without copying arbitrary environment variables or unrelated files.
Missing/mismatched vault keys cause refusal even when an initialized vault is empty.
The running app can continue writing: SQLite's online backup supplies a consistent
database snapshot, including FTS. Keep external configuration and key files stable
while capturing the bundle; they are not part of SQLite's transaction.

Commands print bounded JSON summaries (version/revision, migration, timestamp,
database bytes and counts), never original content or secret values. Success exits
0, validation/I/O failure exits 1, cancellation exits 130; argument errors exit 2.

## Restore separately, then review activation

Use a compatible v0.50.0 installation with the same migration support and enough
private storage. Restore creates the **destination itself**, so it must not exist:

```sh
python -m lifegather.recovery verify /backups/installation.lgbackup --staging-dir /private-staging
python -m lifegather.recovery restore /backups/installation.lgbackup /private/recovered --staging-dir /private-staging
```

The result is `recovered/data/auth.sqlite3`, optional
`recovered/secrets/vault.key`, and `recovered/installation.json`. Files are created
with Unix mode 0600, directories 0700. On Windows, use a parent directory with
appropriate private ACLs; Unix mode arguments do not establish Windows ACLs.
Existing directories, files and final symlinks are refused. Authentication,
manifest/hash, database, original-byte and credential checks all finish before the
destination is created. Handled write failures remove files created by that
attempt. Forced termination/power loss may leave a private incomplete directory;
inspect and preserve it before retrying at another new destination.

Nothing starts, migrates or redeploys automatically. Review recovered account and
session access, connector consent, pending jobs and scan schedules **before**
manually starting an app with this copy: the database preserves their original
state. Review the public URL and OAuth callback registration as well. Use the
restored JSON through `LIFEGATHER_CONFIGURATION_FILE`; it preserves literal `${...}`,
Unicode and newline characters in secrets without dotenv interpolation.

Settings precedence is explicit constructor values, environment, `.env`, JSON,
then file secrets/defaults. Remove stale overrides or set them to the recovered
paths deliberately. In particular the Docker image defaults `LIFEGATHER_DATA_DIR`
to `/data`: mount the recovered data there and the key/configuration separately,
and set `LIFEGATHER_VAULT_KEY_FILE` and `LIFEGATHER_CONFIGURATION_FILE` to their
**container** paths. The JSON's generated absolute paths describe the restore
environment; they are not portable host-to-container mount paths. Static directory
and build revision remain properties of the running image. Keep configuration and
key outside the data/static directories, as required by existing settings checks.
Preserve the original installation until a separate recovery check succeeds.

## Storage and format limits

Temporary plaintext is necessary for snapshot and authenticated verification.
Staging defaults to the configured data directory when it exists, otherwise the
system temporary directory. `--staging-dir` chooses an existing private directory;
never use a served/static location. Allow roughly three extra database sizes during
backup/restore (encrypted output or restored database plus staged copies), with
additional headroom for journals and concurrent growth. The supplied container's
small `/tmp` is unsuitable for large recovery jobs; use the durable data volume or
an explicit sufficiently large private staging mount. Normal completion and
handled failures remove staging files. Secure erasure of SSD/tmpfs pages is not
promised. Keep a verified encrypted copy off the installation's storage.

Format 1 uses the fixed `LIFEGATHER-RECOVERY` magic, zero byte and version byte 1,
16-byte random salt, 12-byte random nonce, AES-256-GCM ciphertext and a 16-byte tag.
The complete header is authenticated. Argon2id derives the 32-byte encryption key
with 64 MiB memory, 3 iterations and 1 lane; parameters are fixed by format, never
selected by an input file. This uses the existing cryptography dependency and no
weaker fallback. See the [Argon2id API](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#argon2id)
and [OWASP password-derived key guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

The authenticated plaintext has a 4-byte big-endian manifest length, a bounded
64 KiB JSON manifest, then fixed ordered database/configuration/optional-key parts.
Each part has an exact length and SHA-256 hash. Configuration is at most 64 KiB;
the key is exactly 32 bytes. It is not a general ZIP/tar archive: arbitrary member
names, links, duplicates, extra data and unsupported formats are refused. No
arbitrary small database cap is imposed; the complete encoded plaintext must fit
GCM's [limit](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=51288) of
64 GiB minus 32 bytes, so the database must be smaller than that.
Larger payloads are refused. Processing streams in 1 MiB chunks and requires disk
space proportional to the installation rather than whole-database RAM. KDF memory
is additional. Plaintext is parsed only after successful GCM authentication.

This release supports migration `0023_asset_consolidation` only; future schema
versions require an explicitly compatible recovery implementation. Original BLOBs
are checked against stored lengths/hashes and every saved credential is decrypted
with its owner-bound authenticated context. SQLite integrity and foreign keys are
checked on a standalone snapshot without application extensions or provider calls.
Encryption does not establish who created a bundle: accept bundles from your own
trusted backup process. Verification does not repair corrupt source data.

## Isolated release check

`scripts/Verify-Recovery.py` creates only synthetic data in a new temporary
directory under `/data`. Against a freshly built image, run it with no network,
read-only root, no capabilities, `/tmp` limited to 64 MiB and `/data` at least
512 MiB. For example, on a POSIX host from this repository, set `IMAGE` to the
verified immutable image tag, then:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=64m,mode=1777 \
  --tmpfs /data:size=512m,uid=10001,gid=10001,mode=0700 \
  --mount "type=bind,source=$(pwd)/scripts/Verify-Recovery.py,target=/verify.py,readonly" \
  --entrypoint python "$IMAGE" /verify.py
```

This exercises the actual CLI with a database larger than 40 MiB, JSON facts,
two owners, photo/document originals, a private credential, restored file permissions
and existing-destination refusal. It never starts the app or opens live storage.
