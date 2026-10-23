"""Read-only validation of complete installation snapshots and original bytes."""

import binascii
import hashlib
import json
import re
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Engine, Table, select
from sqlalchemy.exc import SQLAlchemyError

from lifegather.database import begin_snapshot
from lifegather.memory.backup import (
    RowTransform,
    SnapshotError,
    SnapshotReader,
    application_tables,
    current_migration,
)
from lifegather.recovery.envelope import RecoveryError
from lifegather.storage.base import ObjectStorage, StorageError
from lifegather.storage.originals import verified

SUPPORTED_MIGRATIONS = frozenset(
    {
        "0027_forest_dark_theme",
        "0028_object_storage",
        "0029_receipt_detail_basis",
        "0030_pgvector",
        "0031_conversation_retention",
        "0032_email_attachments",
        "0033_account_row_security",
        "0034_research_findings",
        "0035_research_save_receipts",
        "0036_credential_auth_state",
        "0037_terms_acceptance",
        "0038_operational_events",
        "0039_deleted_accounts",
    }
)
STORED_PARTS = {
    "documents": (("original", "original_key", "size", "content_hash"),),
    "photos": (
        ("original", "original_key", "size", "content_hash"),
        ("preview", "preview_key", "preview_size", None),
    ),
}
DOCUMENT_FORMATS = frozenset({"pdf", "docx", "xlsx", "txt", "md", "csv"})
HASH = re.compile(r"[a-f0-9]{64}")

Rows = Callable[[str], Iterator[dict[str, Any]]]


@dataclass(frozen=True)
class DatabaseSummary:
    migration: str
    users: int
    credentials: int
    photos: int
    documents: int


def _json(value: Any) -> bool:
    try:
        json.loads(value)
    except (TypeError, ValueError, RecursionError):
        return False
    return True


def inline_stored_objects(storage: ObjectStorage) -> RowTransform:
    """Copy stored originals/previews back into snapshot rows as they are written.

    The bundle stays self-contained and independent of the storage backend; a
    restored installation moves the bytes out to its own storage on startup.
    """

    def inline(table: str, row: dict[str, Any]) -> dict[str, Any]:
        for column, key_column, size_column, digest_column in STORED_PARTS.get(
            table, ()
        ):
            key = row[key_column]
            if key is None:
                continue
            row[column] = (
                None
                if row["deleted_at"] is not None
                else verified(
                    storage.get(key),
                    row[size_column],
                    row[digest_column] if digest_column else None,
                )
            )
            row[key_column] = None
        return row

    return inline


def _validate(migration: str, rows: Rows, key: bytes | None) -> DatabaseSummary:
    """Verify schema version, history heads, vault identity and original hashes.

    No migration, provider request or application worker runs during
    verification. Rows stream one at a time; only identifiers are retained.
    """
    if migration not in SUPPORTED_MIGRATIONS:
        raise RecoveryError("Snapshot migration is not supported by this release")
    current_tasks = {
        (row["user_id"], row["task_id"])
        for row in rows("maintenance_revisions")
        if row["superseded_at"] is None
    }
    if any(
        (row["user_id"], row["id"]) not in current_tasks
        for row in rows("maintenance_tasks")
    ):
        raise RecoveryError("Snapshot maintenance history is incomplete")
    if any(
        row.get("basis", "labeled") not in ("labeled", "reviewed")
        for row in rows("receipt_details")
    ):
        raise RecoveryError("Snapshot receipt detail basis is invalid")
    for row in rows("documents"):
        if row["format"] not in DOCUMENT_FORMATS or not _json(
            row["extraction_metadata"]
        ):
            raise RecoveryError("Snapshot document metadata is invalid")
    revisions = set()
    for row in rows("asset_type_revisions"):
        if not _json(row["definition_json"]):
            raise RecoveryError("Snapshot asset type definition is invalid")
        revisions.add((row["user_id"], row["type_id"], row["id"]))
    if any(
        (row["user_id"], row["id"], row["revision"]) not in revisions
        for row in rows("asset_types")
    ):
        raise RecoveryError("Snapshot asset type history is incomplete")

    fingerprints = [(row["id"], row["fingerprint"]) for row in rows("vault_key")]
    credentials = list(rows("credentials"))
    if len(fingerprints) > 1 or (fingerprints and fingerprints[0][0] != 1):
        raise RecoveryError("Snapshot vault identity is invalid")
    if key is not None and len(key) != 32:
        raise RecoveryError("Recovery requires the original 32-byte vault key")
    if fingerprints:
        if key is None or not secrets.compare_digest(
            hashlib.sha256(key).hexdigest(), str(fingerprints[0][1])
        ):
            raise RecoveryError("The original vault key is missing or does not match")
    elif credentials:
        raise RecoveryError("Snapshot credentials have no vault identity")
    if credentials:
        if key is None:
            raise RecoveryError("The original vault key is required")
        cipher = AESGCM(key)
        for row in credentials:
            if (
                not isinstance(row["nonce"], bytes)
                or len(row["nonce"]) != 12
                or not isinstance(row["ciphertext"], bytes)
                or len(row["ciphertext"]) > 32784
                or any(
                    len(row[name]) > limit
                    for name, limit in (
                        ("id", 36),
                        ("user_id", 36),
                        ("kind", 64),
                        ("provider", 64),
                    )
                )
            ):
                raise RecoveryError("Snapshot credential bytes are invalid")
            context = json.dumps(
                [
                    "lifegather-vault-v1",
                    row["user_id"],
                    row["id"],
                    row["kind"],
                    row["provider"],
                ],
                separators=(",", ":"),
            ).encode()
            secret = cipher.decrypt(row["nonce"], row["ciphertext"], context).decode(
                "utf-8"
            )
            if not secret.strip() or len(secret) > 8192:
                raise RecoveryError("Snapshot credential bytes are invalid")

    counts = {}
    for table in ("photos", "documents"):
        count = 0
        for row in rows(table):
            count += 1
            if any(row.get(part[1]) is not None for part in STORED_PARTS[table]):
                # Snapshots must carry every original themselves.
                raise RecoveryError("Snapshot refers to files outside the bundle")
            if not isinstance(row["content_hash"], str) or not HASH.fullmatch(
                row["content_hash"]
            ):
                raise RecoveryError("Snapshot original hash metadata is invalid")
            original = row["original"]
            if table == "photos":
                preview = row["preview"]
                if (row["deleted_at"] is None and preview is None) or (
                    preview is not None and len(preview) != row["preview_size"]
                ):
                    raise RecoveryError(
                        "Snapshot photo preview metadata is inconsistent"
                    )
            if original is None:
                if row["deleted_at"] is None:
                    raise RecoveryError("Snapshot is missing an active original")
                continue
            if row["size"] != len(original):
                raise RecoveryError("Snapshot original length does not match metadata")
            if not secrets.compare_digest(
                hashlib.sha256(original).hexdigest(), row["content_hash"]
            ):
                raise RecoveryError("Snapshot original hash does not match metadata")
        counts[table] = count
    return DatabaseSummary(
        migration=migration,
        users=sum(1 for _ in rows("users")),
        credentials=len(credentials),
        photos=counts["photos"],
        documents=counts["documents"],
    )


def validate_snapshot(path: Path, key: bytes | None) -> DatabaseSummary:
    """Validate a portable snapshot file without any database server."""
    try:
        with path.open("rb") as source:
            reader = SnapshotReader(source)
            return _validate(reader.migration, reader.rows, key)
    except RecoveryError:
        raise
    except (
        SnapshotError,
        InvalidTag,
        KeyError,
        ValueError,
        TypeError,
        binascii.Error,
        OSError,
    ):
        raise RecoveryError("Unable to validate the installation snapshot") from None


def validate_database(
    engine: Engine, key: bytes | None, storage: ObjectStorage | None = None
) -> DatabaseSummary:
    """Validate a live or restored PostgreSQL database in one consistent read.

    With `storage`, stored originals are read and checked as if inlined.
    """
    inline = inline_stored_objects(storage) if storage is not None else None
    try:
        with engine.connect() as connection:
            begin_snapshot(connection)
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            migration = current_migration(connection)
            tables: dict[str, Table] = {
                table.name: table for table in application_tables(connection)
            }

            def rows(name: str) -> Iterator[dict[str, Any]]:
                table = tables.get(name)
                if table is None:
                    raise RecoveryError("Snapshot is missing a required table")
                for row in connection.execution_options(yield_per=100).execute(
                    select(*table.columns)
                ):
                    values = dict(row._mapping)
                    yield inline(name, values) if inline is not None else values

            summary = _validate(migration, rows, key)
            connection.rollback()
            return summary
    except RecoveryError:
        raise
    except StorageError:
        raise RecoveryError("A stored original is missing or does not match") from None
    except (
        SnapshotError,
        InvalidTag,
        KeyError,
        ValueError,
        TypeError,
        SQLAlchemyError,
    ):
        raise RecoveryError("Unable to validate the installation snapshot") from None
