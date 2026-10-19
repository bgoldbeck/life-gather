import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import BinaryIO

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryService
from lifegather.recovery import bundle as bundles
from lifegather.recovery.bundle import FileRecord, RecoveryService
from lifegather.recovery.database import finalize_snapshot
from lifegather.recovery.envelope import RecoveryError, decrypt_file, encrypt_file

PASSWORD = b"synthetic boundary passphrase"


def minimal(tmp_path: Path) -> tuple[AuthStore, RecoveryService, Path]:
    directory = tmp_path / "source"
    store = AuthStore(directory / "auth.sqlite3")
    store.migrate()
    return (
        store,
        RecoveryService(Settings(data_dir=directory)),
        tmp_path / "copy.lgbackup",
    )


@pytest.mark.parametrize(
    "change",
    [
        "format",
        "traversal",
        "length",
        "hash",
        "link",
        "prefix",
        "duplicate",
        "migration",
    ],
)
def test_malformed_authenticated_payloads_never_publish_or_escape(
    tmp_path: Path, change: str
) -> None:
    _, service, bundle = minimal(tmp_path)
    service = RecoveryService(service.settings, staging_dir=tmp_path)
    service.create(bundle, PASSWORD)
    plain = tmp_path / "plain"
    decrypt_file(bundle, plain, PASSWORD)
    payload = plain.read_bytes()
    length = int.from_bytes(payload[:4], "big")
    manifest = json.loads(payload[4 : 4 + length])
    if change == "format":
        manifest["format"] = "lifegather-recovery/2"
    elif change == "migration":
        manifest["migration"] = "future_schema"
    elif change == "traversal":
        manifest["files"]["../escaped"] = manifest["files"].pop("database.sqlite3")
    elif change == "length":
        manifest["files"]["database.sqlite3"]["size"] += 1
    elif change == "hash":
        manifest["files"]["database.sqlite3"]["sha256"] = "0" * 64
    elif change == "link":
        manifest["files"]["database.sqlite3"]["link"] = "../escaped"
    raw = json.dumps(manifest, separators=(",", ":")).encode()
    if change == "duplicate":
        raw = b'{"format":"lifegather-recovery/1",' + raw[1:]
    prefix = (
        bundles.MAX_MANIFEST_BYTES + 1 if change == "prefix" else len(raw)
    ).to_bytes(4, "big")
    plain.write_bytes(prefix + raw + payload[4 + length :])
    forged = tmp_path / "forged.lgbackup"
    with forged.open("xb") as output:
        encrypt_file(plain, output, PASSWORD)
    destination = tmp_path / "restored"
    with pytest.raises(RecoveryError):
        service.restore(forged, destination, PASSWORD)
    assert not destination.exists() and not (tmp_path / "escaped").exists()


def test_encryption_and_restore_io_failures_remove_only_owned_partial_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service, bundle = minimal(tmp_path)
    original_encrypt = encrypt_file

    def fail_encryption(source: Path, output: BinaryIO, password: bytes) -> None:
        output.write(b"partial")
        raise OSError("SYNTHETIC_SECRET")

    monkeypatch.setattr(bundles, "encrypt_file", fail_encryption)
    with pytest.raises(RecoveryError) as error:
        service.create(bundle, PASSWORD)
    assert "SYNTHETIC_SECRET" not in str(error.value) and not bundle.exists()
    monkeypatch.setattr(bundles, "encrypt_file", original_encrypt)
    service.create(bundle, PASSWORD)
    original_copy = bundles._copy_part

    def fail_publishing(
        source: BinaryIO, output: BinaryIO, expected: FileRecord
    ) -> None:
        if Path(str(source.name)).name == "database.sqlite3":
            output.write(b"partial")
            raise OSError("SYNTHETIC_SECRET")
        original_copy(source, output, expected)

    monkeypatch.setattr(bundles, "_copy_part", fail_publishing)
    destination = tmp_path / "restored"
    with pytest.raises(RecoveryError) as error:
        service.restore(bundle, destination, PASSWORD)
    assert "SYNTHETIC_SECRET" not in str(error.value)
    assert not destination.exists() and bundle.is_file()


def test_concurrent_destination_creation_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service, bundle = minimal(tmp_path)
    original = finalize_snapshot

    def concurrent_output(path: Path) -> None:
        original(path)
        bundle.write_bytes(b"Existing concurrent data")

    monkeypatch.setattr(bundles, "finalize_snapshot", concurrent_output)
    with pytest.raises(RecoveryError):
        service.create(bundle, PASSWORD)
    assert bundle.read_bytes() == b"Existing concurrent data"


def test_full_backup_refuses_a_missing_key_even_for_an_empty_configured_vault(
    tmp_path: Path,
) -> None:
    store, service, bundle = minimal(tmp_path)
    PrivateSettings(store.engine, AESGCM.generate_key(bit_length=256))
    with pytest.raises(RecoveryError, match="vault key"):
        service.create(bundle, PASSWORD)
    assert not bundle.exists()


def test_oversized_snapshot_is_refused_before_bundle_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service, bundle = minimal(tmp_path)
    monkeypatch.setattr(bundles, "MAX_PLAINTEXT_BYTES", 100)
    with pytest.raises(RecoveryError, match="size limit"):
        service.create(bundle, PASSWORD)
    assert not bundle.exists()
    assert not list(service.settings.data_dir.glob("lifegather-recovery-*"))


def test_online_backup_is_consistent_during_an_uncommitted_source_transaction(
    tmp_path: Path,
) -> None:
    store, service, bundle = minimal(tmp_path)
    actor = store.login("alice", "alice@example.test", "Alice", now=1).user
    memory = MemoryService(store.engine)
    ready, release = Event(), Event()

    def write_pair() -> None:
        with memory._write() as db:
            memory._ingest_in(
                db, actor, SourceInput(text="Synthetic atomic source first.")
            )
            ready.set()
            if not release.wait(30):
                raise TimeoutError("Synthetic writer was not released")
            memory._ingest_in(
                db, actor, SourceInput(text="Synthetic atomic source second.")
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(write_pair)
        assert ready.wait(10)
        try:
            service.create(bundle, PASSWORD)
        finally:
            release.set()
        future.result(timeout=10)
    assert len(memory.search(actor, "atomic")) == 2
    destination = tmp_path / "restored"
    service.restore(bundle, destination, PASSWORD)
    recovered = AuthStore(destination / "data" / "auth.sqlite3")
    assert MemoryService(recovered.engine).search(actor, "atomic") == []
