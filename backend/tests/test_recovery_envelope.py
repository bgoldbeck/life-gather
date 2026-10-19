from pathlib import Path

import pytest

from lifegather.recovery import envelope
from lifegather.recovery.envelope import (
    HEADER_BYTES,
    MAGIC,
    RecoveryError,
    decrypt_file,
    encrypt_file,
)

PASSWORD = b"synthetic recovery passphrase"


def test_format_limit_refuses_before_encryption_or_plaintext_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = encrypt(tmp_path, b"Synthetic original bytes.")
    monkeypatch.setattr(envelope, "MAX_PLAINTEXT_BYTES", 12)
    destination = tmp_path / "restored"
    with pytest.raises(RecoveryError, match="size limit"):
        decrypt_file(bundle, destination, PASSWORD)
    assert not destination.exists()
    output = tmp_path / "oversized"
    with output.open("xb") as stream:
        with pytest.raises(RecoveryError, match="size limit"):
            encrypt_file(tmp_path / "archive", stream, PASSWORD)
    assert output.read_bytes() == b""


def encrypt(tmp_path: Path, value: bytes) -> Path:
    source = tmp_path / "archive"
    source.write_bytes(value)
    bundle = tmp_path / "encrypted"
    with bundle.open("xb") as output:
        encrypt_file(source, output, PASSWORD)
    return bundle


@pytest.mark.parametrize(
    "value", [b"", b"Synthetic secret" * 180000], ids=["empty", "multi_chunk"]
)
def test_streamed_roundtrip_and_randomized_encryption(
    tmp_path: Path, value: bytes
) -> None:
    bundle = encrypt(tmp_path, value)
    restored = tmp_path / "restored"
    decrypt_file(bundle, restored, PASSWORD)
    assert restored.read_bytes() == value
    second = tmp_path / "second"
    with second.open("xb") as output:
        encrypt_file(tmp_path / "archive", output, PASSWORD)
    assert bundle.read_bytes() != second.read_bytes()


@pytest.mark.parametrize("offset", [0, len(MAGIC), HEADER_BYTES, -1])
def test_tampering_never_leaves_plaintext(tmp_path: Path, offset: int) -> None:
    bundle = encrypt(tmp_path, b"Synthetic original bytes.")
    changed = bytearray(bundle.read_bytes())
    changed[offset] ^= 1
    bundle.write_bytes(changed)
    restored = tmp_path / "restored"
    with pytest.raises(RecoveryError):
        decrypt_file(bundle, restored, PASSWORD)
    assert not restored.exists()


def test_bad_password_truncation_and_existing_destination(tmp_path: Path) -> None:
    bundle = encrypt(tmp_path, b"Synthetic original bytes.")
    restored = tmp_path / "restored"
    with pytest.raises(RecoveryError, match="passphrase"):
        decrypt_file(bundle, restored, b"another synthetic passphrase")
    assert not restored.exists()
    restored.write_bytes(b"Existing data must remain")
    with pytest.raises(FileExistsError):
        decrypt_file(bundle, restored, PASSWORD)
    assert restored.read_bytes() == b"Existing data must remain"
    for length in (0, HEADER_BYTES - 1, HEADER_BYTES + 1):
        short = tmp_path / f"short-{length}"
        short.write_bytes(bundle.read_bytes()[:length])
        destination = tmp_path / f"destination-{length}"
        with pytest.raises(RecoveryError):
            decrypt_file(short, destination, PASSWORD)
        assert not destination.exists()
