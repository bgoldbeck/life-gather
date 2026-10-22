import hashlib
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from database_support import database
from sqlalchemy import text
from stored_files import files
from test_documents import synthetic_pdf
from test_photos import image_bytes

from lifegather.auth.store import AuthStore
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.service import DocumentService
from lifegather.memory.backup import operator_snapshot
from lifegather.photos.service import PhotoService
from lifegather.recovery.database import (
    inline_stored_objects,
    validate_database,
    validate_snapshot,
)
from lifegather.recovery.envelope import RecoveryError
from lifegather.storage.base import StorageError


def snapshot(store: AuthStore, path: Path) -> Path:
    path.unlink(missing_ok=True)
    operator_snapshot(store.engine, path, inline_stored_objects(files(store.engine)))
    return path


def test_recovery_refuses_future_migrations_and_corrupt_document_originals(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    actor = store.login("synthetic", "synthetic@example.test", "Synthetic", now=1).user
    document = DocumentService(store.engine, files(store.engine)).upload(
        actor, synthetic_pdf(), "synthetic.pdf"
    )
    # A snapshot must carry its originals, not only storage keys.
    with pytest.raises(RecoveryError, match="outside the bundle"):
        validate_database(store.engine, None)
    raw = tmp_path / "raw.jsonl"
    operator_snapshot(store.engine, raw)
    with pytest.raises(RecoveryError, match="outside the bundle"):
        validate_snapshot(raw, None)
    copy = tmp_path / "snapshot.jsonl"
    assert validate_snapshot(snapshot(store, copy), None).documents == 1
    with store.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num='future_schema'"))
    with pytest.raises(RecoveryError, match="migration"):
        validate_database(store.engine, None)
    with pytest.raises(RecoveryError, match="migration"):
        validate_snapshot(snapshot(store, copy), None)
    with store.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num='0031_conversation_retention'"))
        db.execute(
            text(
                "UPDATE documents SET original_key=NULL, "
                "original=decode(repeat('00', size::int), 'hex') WHERE id=:id"
            ),
            {"id": document["id"]},
        )
    with pytest.raises(RecoveryError, match="hash"):
        validate_database(store.engine, None)
    with pytest.raises(RecoveryError, match="hash"):
        validate_snapshot(snapshot(store, copy), None)
    store.engine.dispose()


def test_snapshot_inlining_refuses_missing_or_altered_stored_files(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    actor = store.login("synthetic", "synthetic@example.test", "Synthetic", now=1).user
    storage = files(store.engine)
    DocumentService(store.engine, storage).upload(
        actor, synthetic_pdf(), "synthetic.pdf"
    )
    stored = next(path for path in (tmp_path / "files").rglob("*") if path.is_file())
    stored.write_bytes(b"0" * stored.stat().st_size)
    copy = tmp_path / "snapshot.jsonl"
    with pytest.raises(StorageError):
        snapshot(store, copy)
    assert not copy.exists()
    stored.unlink()
    with pytest.raises(StorageError):
        snapshot(store, copy)
    store.engine.dispose()


def test_snapshot_validation_covers_originals_vault_and_owner_bound_ciphertext(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    alice = store.login("alice", "alice@example.test", "Alice", now=1).user
    bob = store.login("bob", "bob@example.test", "Bob", now=1).user
    key = AESGCM.generate_key(bit_length=256)
    vault = PrivateSettings(store.engine, key)
    alice_key = vault.save(alice, "ai", "example", "Synthetic", "synthetic secret")
    bob_key = vault.save(bob, "ai", "example", "Synthetic", "other synthetic secret")
    original = image_bytes()
    photo = PhotoService(store.engine, files(store.engine)).upload(
        alice, original, "synthetic.jpg"
    )
    DocumentService(store.engine, files(store.engine)).upload(
        bob, synthetic_pdf(), "synthetic.pdf"
    )
    copy = tmp_path / "snapshot.jsonl"
    summary = validate_snapshot(snapshot(store, copy), key)
    assert (summary.users, summary.credentials, summary.photos, summary.documents) == (
        2,
        2,
        1,
        1,
    )
    for missing_or_wrong in (None, AESGCM.generate_key(bit_length=256)):
        with pytest.raises(RecoveryError, match="vault key"):
            validate_snapshot(copy, missing_or_wrong)
    with store.engine.begin() as db:
        db.execute(
            text("UPDATE photos SET content_hash=:hash WHERE id=:id"),
            {"hash": "0" * 64, "id": photo["id"]},
        )
    # Stored bytes are checked against their recorded hash while inlining.
    with pytest.raises(StorageError):
        snapshot(store, copy)
    with store.engine.begin() as db:
        db.execute(
            text("UPDATE photos SET content_hash=:hash WHERE id=:id"),
            {
                "hash": hashlib.sha256(original).hexdigest(),
                "id": photo["id"],
            },
        )
        db.execute(
            text(
                "UPDATE credentials SET ciphertext="
                "(SELECT ciphertext FROM credentials WHERE id=:source), "
                "nonce=(SELECT nonce FROM credentials WHERE id=:source) "
                "WHERE id=:target"
            ),
            {"source": alice_key.id, "target": bob_key.id},
        )
    with pytest.raises(RecoveryError, match="validate"):
        validate_snapshot(snapshot(store, copy), key)
    store.engine.dispose()


def test_configured_but_empty_vault_still_needs_its_original_key(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    assert validate_database(store.engine, None).credentials == 0
    key = AESGCM.generate_key(bit_length=256)
    PrivateSettings(store.engine, key)
    with pytest.raises(RecoveryError, match="vault key"):
        validate_database(store.engine, None)
    assert validate_database(store.engine, key).credentials == 0
    store.engine.dispose()


def test_truncated_or_altered_snapshot_files_are_refused(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    store.login("synthetic", "synthetic@example.test", "Synthetic", now=1)
    copy = snapshot(store, tmp_path / "snapshot.jsonl")
    raw = copy.read_bytes()
    for damaged in (raw[:-2], raw + b"[]\n", raw.replace(b'"users"', b'"user"', 1)):
        copy.write_bytes(damaged)
        with pytest.raises(RecoveryError, match="validate"):
            validate_snapshot(copy, None)
    store.engine.dispose()
