import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from stored_files import files
from test_documents import synthetic_pdf
from test_photos import image_bytes

from lifegather.auth.store import AuthStore
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.service import DocumentService
from lifegather.photos.service import PhotoService
from lifegather.recovery.database import inline_stored_objects, validate_database
from lifegather.recovery.envelope import RecoveryError


def test_recovery_refuses_future_migrations_and_corrupt_document_originals(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.sqlite3"
    store = AuthStore(path)
    store.migrate()
    actor = store.login("synthetic", "synthetic@example.test", "Synthetic", now=1).user
    DocumentService(store.engine, files(store.engine)).upload(
        actor, synthetic_pdf(), "synthetic.pdf"
    )
    # A snapshot must carry its originals, not only storage keys.
    with pytest.raises(RecoveryError, match="outside the bundle"):
        validate_database(path, None)
    inline_stored_objects(path, files(store.engine))
    assert validate_database(path, None).documents == 1
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE alembic_version SET version_num='future_schema'")
        db.commit()
    with pytest.raises(RecoveryError, match="migration"):
        validate_database(path, None)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE alembic_version SET version_num='0023_asset_consolidation'")
        db.execute("UPDATE documents SET original=zeroblob(size)")
        db.commit()
    with pytest.raises(RecoveryError, match="hash"):
        validate_database(path, None)


def test_snapshot_validation_covers_originals_vault_and_owner_bound_ciphertext(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.sqlite3"
    store = AuthStore(path)
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
    inline_stored_objects(path, files(store.engine))
    summary = validate_database(path, key)
    assert (summary.users, summary.credentials, summary.photos, summary.documents) == (
        2,
        2,
        1,
        1,
    )
    for missing_or_wrong in (None, AESGCM.generate_key(bit_length=256)):
        with pytest.raises(RecoveryError, match="vault key"):
            validate_database(path, missing_or_wrong)
    with store.engine.begin() as db:
        db.execute(
            text("UPDATE photos SET content_hash=:hash WHERE id=:id"),
            {"hash": "0" * 64, "id": photo["id"]},
        )
    with pytest.raises(RecoveryError, match="hash"):
        validate_database(path, key)
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
        validate_database(path, key)


def test_configured_but_empty_vault_still_needs_its_original_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.sqlite3"
    store = AuthStore(path)
    store.migrate()
    assert validate_database(path, None).credentials == 0
    key = AESGCM.generate_key(bit_length=256)
    PrivateSettings(store.engine, key)
    with pytest.raises(RecoveryError, match="vault key"):
        validate_database(path, None)
    assert validate_database(path, key).credentials == 0
