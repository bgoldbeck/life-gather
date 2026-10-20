"""Synthetic recovery acceptance in an isolated Linux image; never starts the app.

Run with network disabled, a read-only root, /tmp 64 MiB and /data >=512 MiB.
Only a new TemporaryDirectory under /data is used; no existing database is opened.
"""

import json
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import text

from lifegather.auth.store import AuthStore
from lifegather.chat.context import ContextRead, ContextRef, WorkspaceContexts
from lifegather.chat.organizer import OrganizationAction, WorkspaceOrganizer
from lifegather.chat.privacy import ConversationDelete, ConversationPrivacy
from lifegather.chat.service import ChatService, TurnInput
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings, read_key
from lifegather.documents.service import DocumentService
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoService
from lifegather.profiles.service import ProfileChange, ProfileService
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
    custom = ProfileService(store.engine).save(
        alice,
        ProfileChange(
            entity_id=item.id,
            field="custom",
            custom_name="Tire size",
            value="205/55R16",
            text="Synthetic tire label: 205/55R16.",
            operation_key="tire",
        ),
    )
    previous_custom = custom
    snapshot = WorkspaceContexts(store.engine).read(
        alice, ContextRead(page="Assets", entity_id=item.id)
    )
    command = OrganizationAction(
        request_id="synthetic-chat-tire",
        text='Set custom "Tire size" to 215/55R16',
        context=ContextRef(
            page="Assets", entity_id=item.id, version=snapshot["version"]
        ),
    )
    organizer = WorkspaceOrganizer(store.engine)
    changed = organizer.run(alice, command)
    assert organizer.run(alice, command) == changed
    custom = next(
        detail
        for detail in ProfileService(store.engine).get(alice, item.id)["facts"]
        if detail.id == changed["profile_fact_id"]
    )
    assert custom.replaces_id == previous_custom.id and custom.value == "215/55R16"
    chat = ChatService(store.engine)
    removed_conversation = chat.create(alice)["id"]
    transient, _ = chat.begin(
        alice,
        removed_conversation,
        TurnInput(
            request_id="synthetic-deletion",
            mode="search",
            text="Synthetic ephemeral transcript to remove",
        ),
    )
    chat.finish(alice, transient["id"], {"text": "Synthetic ephemeral reply to remove"})
    privacy = ConversationPrivacy(store.engine)
    deletion = ConversationDelete(
        preview_token=privacy.preview(alice, removed_conversation)["preview_token"],
        confirmed=True,
    )
    assert privacy.delete(alice, removed_conversation, deletion)["deleted"]
    assert privacy.delete(alice, removed_conversation, deletion)["deleted"]
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
    personal = PersonalArchive(store.engine).download(alice)
    assert len(personal) < 100000
    with ZipFile(BytesIO(personal)) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert len(manifest["originals"]) == 1
        original = manifest["originals"][0]
        assert original["id"] == photo["id"]
        assert package.read(original["path"]) == image.getvalue()
        assert custom.id.encode() in package.read("records.json")
    assert document["id"].encode() not in personal
    assert b"Synthetic ephemeral transcript to remove" not in personal
    os.environ["LIFEGATHER_DATA_DIR"] = str(source)
    os.environ["LIFEGATHER_VAULT_KEY_FILE"] = str(key_path)
    phrase = root / "phrase"
    phrase.write_text("synthetic recovery passphrase\n", encoding="utf-8")
    phrase.chmod(0o600)
    bundle = root / "copy.lgbackup"
    flags = ["--passphrase-file", str(phrase)]
    assert main(["backup", str(bundle), *flags]) == 0
    assert bundle.stat().st_size > 40 * 1024 * 1024
    # Recovery must not require a secret that existed only in a now-lost config.
    os.environ["LIFEGATHER_GOOGLE_CLIENT_ID"] = "SYNTHETIC_PARTIAL_ID"
    os.environ["LIFEGATHER_CONFIGURATION_FILE"] = str(root / "lost.json")
    assert main(["verify", str(bundle), *flags]) == 0
    destination = root / "recovered"
    assert main(["restore", str(bundle), str(destination), *flags]) == 0
    assert main(["restore", str(bundle), str(destination), *flags]) == 1
    os.environ.pop("LIFEGATHER_GOOGLE_CLIENT_ID")
    os.environ.pop("LIFEGATHER_CONFIGURATION_FILE")
    settings = Settings(
        configuration_file=destination / "installation.json",
        data_dir=destination / "data",
        vault_key_file=destination / "secrets" / "vault.key",
    )
    assert read_key(settings.vault_key_file) == key
    recovered = AuthStore(settings.data_dir / "auth.sqlite3")
    assert ConversationPrivacy(recovered.engine).delete(
        alice, removed_conversation, deletion
    )["deleted"]
    assert ChatService(recovered.engine).conversations(alice)["items"] == []
    recall = MemoryService(recovered.engine)
    assert recall.timeline(alice, item.id)[0].model_dump() == fact.model_dump()
    assert any(
        detail.model_dump() == custom.model_dump()
        for detail in ProfileService(recovered.engine).get(alice, item.id)["facts"]
    )
    assert any(
        detail.id == previous_custom.id and detail.value == "205/55R16"
        for detail in ProfileService(recovered.engine).get(
            alice, item.id, history=True
        )["facts"]
    )
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
