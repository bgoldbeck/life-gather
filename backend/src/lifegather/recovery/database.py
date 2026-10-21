"""Read-only validation of complete installation snapshots and original bytes."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lifegather.recovery.envelope import CHUNK_BYTES, RecoveryError

SUPPORTED_MIGRATIONS = frozenset(
    {
        "0023_asset_consolidation",
        "0024_maintenance",
        "0025_document_formats",
        "0026_asset_types",
    }
)


@dataclass(frozen=True)
class DatabaseSummary:
    migration: str
    users: int
    credentials: int
    photos: int
    documents: int


def connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    # Keep SQLite's built-in JSON checks available: the supported Linux SQLite
    # rejects json_valid() in CHECK constraints with trusted_schema=OFF. This is
    # a fresh connection with no application functions or extensions loaded;
    # query_only and mode=ro prevent writes during validation.
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def finalize_snapshot(path: Path) -> None:
    """Normalize only the private copied snapshot into a standalone database."""
    try:
        with closing(sqlite3.connect(path)) as db:
            if db.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise RecoveryError("Unable to prepare a standalone snapshot")
    except sqlite3.Error:
        raise RecoveryError("Unable to prepare a standalone snapshot") from None


def validate_database(
    path: Path, key: bytes | None, *, standalone: bool = False
) -> DatabaseSummary:
    """Verify existing schema, ownership constraints, vault and original hashes.

    No migration, provider request or application worker runs during verification.
    Original BLOBs are read in chunks rather than loading the database into memory.
    """
    try:
        if standalone:
            with path.open("rb") as source:
                header = source.read(100)
            if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
                raise RecoveryError("Recovery requires a standalone SQLite snapshot")
        with closing(connect_readonly(path)) as db:
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RecoveryError("Snapshot integrity check failed")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RecoveryError("Snapshot ownership constraints are inconsistent")
            revisions = db.execute(
                "SELECT version_num FROM alembic_version LIMIT 2"
            ).fetchall()
            if len(revisions) != 1 or revisions[0][0] not in SUPPORTED_MIGRATIONS:
                raise RecoveryError(
                    "Snapshot migration is not supported by this release"
                )
            if revisions[0][0] in (
                "0024_maintenance",
                "0025_document_formats",
                "0026_asset_types",
            ):
                # A current schema marker must include complete typed task storage.
                # Older accepted snapshots deliberately need no maintenance tables.
                db.execute(
                    "SELECT id,entity_id,source_id,request_id,fingerprint,recorded_at "
                    "FROM maintenance_tasks LIMIT 0"
                )
                db.execute(
                    "SELECT id,task_id,previous_id,title,due_on,timezone,state,"
                    "completed_on,source_id,request_id,fingerprint,recorded_at,"
                    "superseded_at FROM maintenance_revisions LIMIT 0"
                )
                if db.execute(
                    "SELECT 1 FROM maintenance_tasks t WHERE NOT EXISTS ("
                    "SELECT 1 FROM maintenance_revisions r WHERE r.user_id=t.user_id "
                    "AND r.task_id=t.id AND r.superseded_at IS NULL) LIMIT 1"
                ).fetchone():
                    raise RecoveryError("Snapshot maintenance history is incomplete")
            if revisions[0][0] in ("0025_document_formats", "0026_asset_types"):
                if db.execute(
                    "SELECT 1 FROM documents WHERE format NOT IN "
                    "('pdf','docx','xlsx','txt','md','csv') "
                    "OR NOT json_valid(extraction_metadata) LIMIT 1"
                ).fetchone():
                    raise RecoveryError("Snapshot document metadata is invalid")
            if revisions[0][0] == "0026_asset_types":
                db.execute(
                    "SELECT id,type_id,name,system_field,retired,position "
                    "FROM asset_type_fields LIMIT 0"
                )
                db.execute(
                    "SELECT id,type_id,previous_id,request_id,fingerprint,"
                    "definition_json,recorded_at FROM asset_type_revisions LIMIT 0"
                )
                if db.execute(
                    "SELECT 1 FROM asset_types t WHERE NOT EXISTS "
                    "(SELECT 1 FROM asset_type_revisions r WHERE r.user_id=t.user_id "
                    "AND r.type_id=t.id AND r.id=t.revision) LIMIT 1"
                ).fetchone():
                    raise RecoveryError("Snapshot asset type history is incomplete")
                if db.execute(
                    "SELECT 1 FROM asset_type_revisions "
                    "WHERE NOT json_valid(definition_json) LIMIT 1"
                ).fetchone():
                    raise RecoveryError("Snapshot asset type definition is invalid")
            fingerprints = db.execute(
                "SELECT id,fingerprint FROM vault_key LIMIT 2"
            ).fetchall()
            credential_count = db.execute(
                "SELECT count(*) FROM credentials"
            ).fetchone()[0]
            if len(fingerprints) > 1 or (fingerprints and fingerprints[0][0] != 1):
                raise RecoveryError("Snapshot vault identity is invalid")
            if key is not None and len(key) != 32:
                raise RecoveryError("Recovery requires the original 32-byte vault key")
            if fingerprints:
                if key is None or not secrets.compare_digest(
                    hashlib.sha256(key).hexdigest(), str(fingerprints[0][1])
                ):
                    raise RecoveryError(
                        "The original vault key is missing or does not match"
                    )
            elif credential_count:
                raise RecoveryError("Snapshot credentials have no vault identity")
            if credential_count:
                if key is None:
                    raise RecoveryError("The original vault key is required")
                malformed = db.execute(
                    "SELECT 1 FROM credentials WHERE length(nonce) != 12 "
                    "OR length(ciphertext) > 32784 OR length(id) > 36 "
                    "OR length(user_id) > 36 OR length(kind) > 64 "
                    "OR length(provider) > 64 LIMIT 1"
                ).fetchone()
                if malformed:
                    raise RecoveryError("Snapshot credential bytes are invalid")
                cipher = AESGCM(key)
                for identifier, owner, kind, provider, nonce, ciphertext in db.execute(
                    "SELECT id,user_id,kind,provider,nonce,ciphertext FROM credentials"
                ):
                    context = json.dumps(
                        ["lifegather-vault-v1", owner, identifier, kind, provider],
                        separators=(",", ":"),
                    ).encode()
                    secret = cipher.decrypt(nonce, ciphertext, context).decode("utf-8")
                    if not secret.strip() or len(secret) > 8192:
                        raise RecoveryError("Snapshot credential bytes are invalid")
            counts = {}
            for table in ("photos", "documents"):
                if db.execute(
                    f"SELECT 1 FROM {table} WHERE length(content_hash) != 64 LIMIT 1"
                ).fetchone():
                    raise RecoveryError("Snapshot original hash metadata is invalid")
                count = 0
                for (
                    rowid,
                    size,
                    expected,
                    deleted_at,
                    present,
                    stored_size,
                ) in db.execute(
                    "SELECT rowid,size,content_hash,deleted_at,"
                    f"original IS NOT NULL,length(original) FROM {table}"
                ):
                    count += 1
                    if not present:
                        if deleted_at is None:
                            raise RecoveryError(
                                "Snapshot is missing an active original"
                            )
                        continue
                    if size != stored_size:
                        raise RecoveryError(
                            "Snapshot original length does not match metadata"
                        )
                    digest = hashlib.sha256()
                    with db.blobopen(
                        table, "original", rowid, readonly=True
                    ) as original:
                        while block := original.read(CHUNK_BYTES):
                            digest.update(block)
                    if not secrets.compare_digest(digest.hexdigest(), str(expected)):
                        raise RecoveryError(
                            "Snapshot original hash does not match metadata"
                        )
                counts[table] = count
            if db.execute(
                "SELECT 1 FROM photos WHERE (deleted_at IS NULL AND preview IS NULL) "
                "OR (preview IS NOT NULL AND length(preview) != preview_size) LIMIT 1"
            ).fetchone():
                raise RecoveryError("Snapshot photo preview metadata is inconsistent")
            return DatabaseSummary(
                migration=revisions[0][0],
                users=db.execute("SELECT count(*) FROM users").fetchone()[0],
                credentials=credential_count,
                photos=counts["photos"],
                documents=counts["documents"],
            )
    except RecoveryError:
        raise
    except (sqlite3.Error, InvalidTag, ValueError, TypeError, OSError):
        raise RecoveryError("Unable to validate the installation snapshot") from None
