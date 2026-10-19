# Next increment: encrypted operator backup and recovery

Prepared October 19, 2026 after source acceptance of consolidation v0.48.0.
Baseline: main 141c28601727ccb23f0c3e15044472ba1607cbaa, v0.48.0, migration 0023. Main/branches and open PRs checked; no competing recovery implementation exists. This scope is published before implementation; acceptance is not yet complete.

## Evidence and value

The existing `operator_snapshot` creates an online consistent SQLite backup and
checks integrity. Photos and PDFs store their original bytes in SQLite, so the
snapshot already contains them. Personal JSON downloads deliberately exclude
originals, account/authentication data and credentials and cannot be restored.
The server vault key must live outside data/static directories; installation
configuration is also external. Existing restore instructions require manual
coordination and provide no executable recovery validation.

The valuable next slice is an operator-only command that creates an encrypted
recovery bundle, verifies it, and restores into a fresh private directory. It
should reuse the existing snapshot rather than invent another data export.

## Proposed boundaries

- Framework-independent backup service plus explicit CLI; no HTTP/MCP/model tool
  exposing all users' records. This is installation recovery, with every owner's
  data and authentication state, not personal record import.
- Versioned encrypted bundle with manifest, consistent SQLite snapshot, explicit
  installation configuration and the separate vault key when configured. Do not
  infer arbitrary external files or include unrelated environment variables.
- Authenticated streaming encryption using existing cryptography dependency and
  a passphrase-derived key; avoid a whole-database memory requirement. Prompt for
  a passphrase or read an explicit protected passphrase file; never print it or
  put it in command-line arguments. Restrictive permissions for temporary files.
- Validate authenticated format, supported versions/migration, file names, lengths,
  hashes, SQLite integrity/foreign keys and original-byte metadata. Reject corrupt,
  incomplete, oversized metadata or newer unsupported bundles before restoration.
- Restore only into a new directory, with data, secrets and configuration separated
  to preserve the current vault-key placement rule. Refuse existing destinations,
  archive traversal, links and unexpected members. Leave running installations
  untouched; do not start the app, call providers or deploy automatically.
- Keep original IDs, evidence/history, exact monetary values, separate physical
  units, owner boundaries and credential decryptability. Document restored pending
  jobs/schedules and auth state explicitly rather than silently rewriting them.
- Portable configuration must point at restored paths; preserve necessary secrets
  inside encryption. Backup/verify/restore output contains summaries, no content
  or credential values. No additional runtime dependency or schema is expected.

## Acceptance evidence to gather

An isolated two-owner synthetic installation with photo/PDF originals, a correction,
consolidation/reversal, exact JPY receipt claims and a synthetic encrypted credential
must survive backup, verification and fresh-directory restoration. Compare original
bytes/hashes, IDs, history, owner-isolated recall/search and vault decryption. Test
online write consistency, wrong passphrase, tampering/truncation, invalid paths,
unsupported version, missing/wrong key and existing destinations; failures must
leave no usable partial restore or overwrite source data. Exercise CLI exit codes
and secret-safe output. Run applicable complete checks, package and container
recovery smoke, then graph refresh and the standing source/release sequence.

Before implementation, recheck current main/branches/open PRs, reread the current
plan, publish a meaningful early scope commit on a new branch, and confirm local
cryptography API signatures. Continue checking account usage between milestones.
