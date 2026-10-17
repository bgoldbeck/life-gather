from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from lifegather.auth.store import AuthStore
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings, VaultError


def test_owner_scoping_ciphertext_binding_and_persistence(tmp_path: Path) -> None:
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "A", now=1).user
    bob = auth.login("bob", "b@example.test", "B", now=1).user
    key = AESGCM.generate_key(bit_length=256)
    service = PrivateSettings(auth.engine, key)
    entry = service.save(alice, "ai", "example", "Personal", "synthetic-secret")
    assert service.list(bob)["items"] == []
    assert service.read_secret(alice, entry.id) == "synthetic-secret"
    with pytest.raises(VaultError):
        service.read_secret(bob, entry.id)
    with pytest.raises(VaultError):
        service.replace(bob, entry.id, "attacker")
    with pytest.raises(VaultError):
        service.remove(bob, entry.id)
    with Session(auth.engine) as db:
        row = db.scalar(select(Credential).where(Credential.id == entry.id))
        assert row is not None
        assert b"synthetic-secret" not in row.ciphertext
    restarted = PrivateSettings(auth.engine, key)
    assert restarted.read_secret(alice, entry.id) == "synthetic-secret"
    service.replace(alice, entry.id, "replacement")
    assert service.read_secret(alice, entry.id) == "replacement"
    with pytest.raises(VaultError):
        PrivateSettings(auth.engine, AESGCM.generate_key(256)).read_secret(
            alice, entry.id
        )
    # Even copying ciphertext onto another owner's credential must not decrypt.
    other = service.save(bob, "ai", "example", "Other", "other-secret")
    with auth.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE credentials SET ciphertext="
                "(SELECT ciphertext FROM credentials WHERE id=:a), "
                "nonce=(SELECT nonce FROM credentials WHERE id=:a) WHERE id=:b"
            ),
            {"a": entry.id, "b": other.id},
        )
    with pytest.raises(VaultError):
        service.read_secret(bob, other.id)
    service.remove(alice, entry.id)
    with pytest.raises(VaultError):
        service.read_secret(alice, entry.id)


def test_preferences_are_separate_and_missing_key_is_safe(tmp_path: Path) -> None:
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "A", now=1).user
    bob = auth.login("bob", "b@example.test", "B", now=1).user
    service = PrivateSettings(auth.engine, None)
    assert service.preferences(alice) is False
    service.set_preferences(alice, True)
    assert service.preferences(alice) is True
    assert service.preferences(bob) is False
    with pytest.raises(VaultError):
        service.save(alice, "ai", "example", "Personal", "secret")


def test_pagination_quota_and_removal_without_key(tmp_path: Path) -> None:
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "A", now=1).user
    bob = auth.login("bob", "b@example.test", "B", now=1).user
    service = PrivateSettings(auth.engine, AESGCM.generate_key(256))
    for index in range(100):
        service.save(alice, "ai", "example", str(index), "synthetic")
    with pytest.raises(VaultError, match="limit"):
        service.save(alice, "ai", "example", "overflow", "synthetic")
    # Another user's quota remains independent.
    service.save(bob, "ai", "example", "Bob", "synthetic")
    first = service.list(alice, limit=60)
    second = service.list(alice, cursor=first["next_cursor"] or "", limit=60)
    assert len(first["items"]) == 60 and len(second["items"]) == 40
    assert second["next_cursor"] is None
    assert len({item["id"] for item in first["items"] + second["items"]}) == 100
    unavailable = PrivateSettings(auth.engine, None)
    credential_id = str(first["items"][0]["id"])
    unavailable.remove(alice, credential_id)
    assert len(service.list(alice, limit=100)["items"]) == 99


def test_key_paths_reject_private_or_public_storage(tmp_path: Path) -> None:
    from lifegather.config import Settings
    from lifegather.credentials.service import read_key

    data = tmp_path / "data"
    with pytest.raises(ValueError, match="outside"):
        Settings(data_dir=data, vault_key_file=data / "vault.key")
    static = tmp_path / "static"
    with pytest.raises(ValueError, match="outside"):
        Settings(data_dir=data, static_dir=static, vault_key_file=static / "vault.key")
    invalid = tmp_path / "invalid.key"
    invalid.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="32-byte"):
        read_key(invalid)
    assert read_key(None) is None
