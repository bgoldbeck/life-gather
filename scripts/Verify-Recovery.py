"""Synthetic recovery acceptance in an isolated Linux image; never starts the app.

Run with network disabled, a read-only root, /tmp 64 MiB and /data >=512 MiB.
Only a new TemporaryDirectory under /data is used; no existing database is opened.
"""

import json
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import text

from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings, read_key
from lifegather.documents.service import DocumentService
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoService
from lifegather.recovery.__main__ import main
from lifegather.version import __version__


def verify(root: Path) -> None:
    source = root / "source"
    store = AuthStore(source / "auth.sqlite3")
    store.migrate()
    alice = store.login("synthetic-a", "a@example.test", "Synthetic A", now=1).user
    bob = store.login("synthetic-b", "b@example.test", "Synthetic B", now=1).user
    memory = MemoryService(store.engine)
    evidence = memory.ingest(alice, SourceInput(text="Synthetic JSON recovery proof."))
    item = memory.create_entity(
        alice,
        EntityInput(
            name="Synthetic item",
            kind="asset",
            source_id=evidence.id,
            operation_key="item",
        ),
    )
    fact = memory.assert_fact(
        alice,
        FactInput(
            subject_id=item.id,
            predicate="owned",
            value=True,
            source_id=evidence.id,
            operation_key="owned",
        ),
    )
    key = AESGCM.generate_key(bit_length=256)
    key_path = root / "source.key"
    key_path.write_bytes(key)
    vault = PrivateSettings(store.engine, key)
    credential = vault.save(alice, "ai", "example", "Synthetic", "synthetic secret")
    image = BytesIO()
    Image.new("RGB", (12, 12), "blue").save(image, "JPEG")
    photo = PhotoService(store.engine).upload(alice, image.getvalue(), "synthetic.jpg")
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.write(pdf)
    document = DocumentService(store.engine).upload(
        bob, pdf.getvalue(), "synthetic.pdf"
    )
    with store.engine.begin() as db:
        db.execute(text("CREATE TABLE synthetic_padding (value BLOB)"))
        db.execute(text("INSERT INTO synthetic_padding VALUES (zeroblob(41943040))"))
    os.environ["LIFEGATHER_DATA_DIR"] = str(source)
    os.environ["LIFEGATHER_VAULT_KEY_FILE"] = str(key_path)
    phrase = root / "phrase"
    phrase.write_text("synthetic recovery passphrase\n", encoding="utf-8")
    phrase.chmod(0o600)
    bundle = root / "copy.lgbackup"
    flags = ["--passphrase-file", str(phrase)]
    assert main(["backup", str(bundle), *flags]) == 0
    assert bundle.stat().st_size > 40 * 1024 * 1024
    assert main(["verify", str(bundle), *flags]) == 0
    destination = root / "recovered"
    assert main(["restore", str(bundle), str(destination), *flags]) == 0
    assert main(["restore", str(bundle), str(destination), *flags]) == 1
    settings = Settings(
        configuration_file=destination / "installation.json",
        data_dir=destination / "data",
        vault_key_file=destination / "secrets" / "vault.key",
    )
    assert read_key(settings.vault_key_file) == key
    recovered = AuthStore(settings.data_dir / "auth.sqlite3")
    recall = MemoryService(recovered.engine)
    assert recall.timeline(alice, item.id)[0].model_dump() == fact.model_dump()
    try:
        recall.get_entity(bob, item.id)
    except MemoryError:
        pass
    else:
        raise AssertionError("Synthetic owner isolation failed")
    assert (
        PhotoService(recovered.engine).binary(alice, photo["id"], True)[0]
        == image.getvalue()
    )
    assert (
        DocumentService(recovered.engine).binary(bob, document["id"]) == pdf.getvalue()
    )
    assert (
        PrivateSettings(recovered.engine, key).read_secret(alice, credential.id)
        == "synthetic secret"
    )
    with recovered.engine.connect() as db:
        assert (
            db.scalar(text("SELECT length(value) FROM synthetic_padding")) == 41943040
        )
    for path in (
        destination / "data" / "auth.sqlite3",
        destination / "installation.json",
        settings.vault_key_file,
    ):
        assert path is not None and path.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o700
    assert not list(source.glob("lifegather-recovery-*"))
    store.engine.dispose()
    recovered.engine.dispose()
    print(
        json.dumps(
            {
                "result": "passed",
                "version": __version__,
                "database_min_bytes": 41943040,
                "network": "none",
            }
        )
    )


if __name__ == "__main__":
    with TemporaryDirectory(prefix="recovery-smoke-", dir="/data") as directory:
        verify(Path(directory))
