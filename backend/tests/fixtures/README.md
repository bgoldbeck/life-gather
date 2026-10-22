Synthetic data only. They test the one-time PostgreSQL import and the restore of
SQLite-era (format 1) recovery bundles; the bundles use the passphrase
`synthetic legacy passphrase`. Both were produced from the synthetic installation
in `test_recovery_bundle.installation`, plus one note for Bob.

- `legacy-0027.*`: LifeGather 0.64.0, schema `0027_forest_dark_theme`, originals
  inside the SQLite database.
- `legacy-0029/` and `legacy-0029.*`: LifeGather 0.70.0, schema
  `0029_receipt_detail_basis` (unchanged through 0.74, the last SQLite
  release). The directory is a `/data` folder: the SQLite database plus the
  originals it keeps in `files/`.
