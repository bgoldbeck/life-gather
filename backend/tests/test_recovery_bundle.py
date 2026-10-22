import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_photos import image_bytes
from test_purchase_details import accepted, body

from lifegather.assets.consolidation import (
    Consolidate,
    ConsolidationService,
    ReverseConsolidation,
)
from lifegather.auth.store import Account, AuthStore
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings, VaultError, read_key
from lifegather.documents.models import Document
from lifegather.documents.service import DocumentService
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoService
from lifegather.profiles.service import ProfileChange, ProfileService
from lifegather.reconciliation.models import Binding
from lifegather.reconciliation.purchase_details import DetailRead, PurchaseDetails
from lifegather.recovery.bundle import RecoveryService
from lifegather.recovery.envelope import RecoveryError
from lifegather.storage.originals import move_inline_originals

PASSWORD = b"synthetic recovery password"
LITERAL_SECRET = "Synthetic ${DO_NOT_EXPAND}\n雪"


@dataclass
class Installation:
    store: AuthStore
    alice: Account
    bob: Account
    settings: Settings
    key: bytes
    credential: str
    photo: str
    document: str
    primary: str
    secondary: str
    choice: str
    receipt: str
    facts: list[dict[str, Any]]
    photo_original: bytes
    document_original: bytes
    units: list[tuple[str, str, int]]


def unit_bindings(store: AuthStore) -> list[tuple[str, str, int]]:
    with Session(store.engine) as db:
        return [
            (decision, asset, unit)
            for decision, asset, unit in db.execute(
                select(Binding.decision_id, Binding.asset_id, Binding.unit).order_by(
                    Binding.decision_id, Binding.unit
                )
            )
        ]


def installation(tmp_path: Path) -> Installation:
    directory = tmp_path / "source"
    store = AuthStore(directory / "auth.sqlite3")
    store.migrate()
    alice = store.login("alice", "alice@example.test", "Alice", now=1).user
    bob = store.login("bob", "bob@example.test", "Bob", now=1).user
    key = AESGCM.generate_key(bit_length=256)
    key_path = tmp_path / "source.key"
    key_path.write_bytes(key)
    vault = PrivateSettings(store.engine, key)
    credential = vault.save(
        alice, "ai", "example", "Synthetic", "synthetic recovery credential"
    )
    vault.set_preferences(alice, True)
    memory = MemoryService(store.engine)

    source = memory.ingest(
        alice, SourceInput(text="Synthetic mower identity evidence.")
    )
    pair = [
        memory.create_entity(
            alice,
            EntityInput(
                name=name, kind="asset", source_id=source.id, operation_key=name
            ),
        )
        for name in ("Manual mower", "Receipt mower")
    ]
    profiles = ProfileService(store.engine)
    old = profiles.save(
        alice,
        ProfileChange(
            entity_id=pair[0].id,
            field="paint",
            value="Red",
            text="Synthetic original Red paint.",
            operation_key="red",
        ),
    )
    profiles.save(
        alice,
        ProfileChange(
            entity_id=pair[0].id,
            field="paint",
            value="Blue",
            text="Synthetic corrected Blue paint.",
            operation_key="blue",
            replaces_id=old.id,
        ),
    )
    photo_original = image_bytes()
    document_original = synthetic_pdf()
    photo = PhotoService(store.engine, files(store.engine)).upload(
        alice, photo_original, "synthetic.jpg", asset_id=pair[0].id
    )
    document = DocumentService(store.engine, files(store.engine)).upload(
        bob, document_original, "synthetic.pdf"
    )
    money = "Acme Drill Qty: 2; Line total: JPY 1200"
    receipt = accepted(
        store.engine, alice, money + "\nAcme Saw Qty: 1\nPurchase date: 2026-10-18"
    )
    PurchaseDetails(store.engine).save(
        alice, body(receipt, currency="JPY", line_total="1200", money_quote=money)
    )
    choices = ConsolidationService(store.engine)
    preview = choices.preview(alice, pair[0].id, pair[1].id)
    choice = choices.apply(
        alice,
        Consolidate(
            primary_id=pair[0].id,
            secondary_id=pair[1].id,
            preview_token=preview["preview_token"],
            request_id="join",
            note="Same synthetic item.",
            same_item_confirmed=True,
        ),
    )
    settings = Settings(
        data_dir=directory,
        vault_key_file=key_path,
        google_client_id="synthetic",
        google_client_secret=SecretStr(LITERAL_SECRET),
    )
    return Installation(
        store,
        alice,
        bob,
        settings,
        key,
        credential.id,
        photo["id"],
        document["id"],
        pair[0].id,
        pair[1].id,
        choice["id"],
        receipt["id"],
        [fact.model_dump() for fact in memory.timeline(alice, pair[0].id)],
        photo_original,
        document_original,
        unit_bindings(store),
    )


def test_complete_encrypted_backup_restores_owners_originals_history_money_and_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = installation(tmp_path)
    service = RecoveryService(case.settings)
    bundle = tmp_path / "installation.lgbackup"
    saved = service.create(bundle, PASSWORD)
    assert service.verify(bundle, PASSWORD) == saved
    assert saved.database.users == 2 and saved.database.credentials == 1
    encrypted = bundle.read_bytes()
    assert (
        b"synthetic recovery credential" not in encrypted and case.key not in encrypted
    )
    destination = tmp_path / "restored"
    assert service.restore(bundle, destination, PASSWORD) == saved
    for name in list(os.environ):
        if name.startswith("LIFEGATHER_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    configuration = Settings(configuration_file=destination / "installation.json")
    assert configuration.data_dir == destination / "data"
    assert configuration.google_client_secret.get_secret_value() == LITERAL_SECRET
    assert read_key(configuration.vault_key_file) == case.key
    recovered = AuthStore(configuration.data_dir / "auth.sqlite3")
    memory = MemoryService(recovered.engine)
    assert [
        fact.model_dump() for fact in memory.timeline(case.alice, case.primary)
    ] == case.facts
    assert memory.get_entity(case.alice, case.secondary).id == case.primary
    vault = PrivateSettings(recovered.engine, read_key(configuration.vault_key_file))
    assert (
        vault.read_secret(case.alice, case.credential)
        == "synthetic recovery credential"
    )
    assert vault.preferences(case.alice)
    with pytest.raises(VaultError):
        vault.read_secret(case.bob, case.credential)
    # The bundle carries originals inline; the restored app moves them out again.
    assert not (destination / "data" / "files").exists()
    assert move_inline_originals(recovered.engine, files(recovered.engine)) == 2
    with Session(case.store.engine) as db:
        assert db.scalar(select(Document.original_key)) is not None
    photos = PhotoService(recovered.engine, files(recovered.engine))
    assert photos.binary(case.alice, case.photo, True)[0] == case.photo_original
    with pytest.raises(MemoryError):
        photos.get(case.bob, case.photo)
    documents = DocumentService(recovered.engine, files(recovered.engine))
    assert documents.binary(case.bob, case.document) == case.document_original
    with pytest.raises(MemoryError):
        documents.binary(case.alice, case.document)
    detail = PurchaseDetails(recovered.engine).get(
        case.alice, DetailRead(receipt_id=case.receipt, index=0)
    )
    assert detail["quantity"] == 2
    assert len(case.units) == 3 and len({row[1] for row in case.units}) == 3
    assert unit_bindings(recovered) == case.units
    assert (
        detail["items"][0]["total_minor"] == 1200
        and detail["items"][0]["currency"] == "JPY"
    )
    ConsolidationService(recovered.engine).reverse(
        case.alice,
        ReverseConsolidation(
            consolidation_id=case.choice,
            request_id="separate",
            note="Separate the recovered synthetic records.",
        ),
    )
    assert memory.get_entity(case.alice, case.secondary).id == case.secondary
    assert (
        MemoryService(case.store.engine).get_entity(case.alice, case.secondary).id
        == case.primary
    )


def test_rejected_recovery_never_overwrites_existing_files_or_creates_a_partial_target(
    tmp_path: Path,
) -> None:
    case = installation(tmp_path)
    service = RecoveryService(case.settings)
    bundle = tmp_path / "installation.lgbackup"
    service.create(bundle, PASSWORD)
    before = bundle.read_bytes()
    with pytest.raises(RecoveryError, match="new recovery"):
        service.create(bundle, PASSWORD)
    assert bundle.read_bytes() == before
    destination = tmp_path / "restored"
    with pytest.raises(RecoveryError, match="passphrase"):
        service.restore(bundle, destination, b"wrong synthetic password")
    assert not destination.exists()
    destination.mkdir()
    important = destination / "important"
    important.write_text("Existing data", encoding="utf-8")
    with pytest.raises(RecoveryError, match="new recovery"):
        service.restore(bundle, destination, PASSWORD)
    assert important.read_text(encoding="utf-8") == "Existing data"


def test_backup_refuses_a_missing_stored_original(tmp_path: Path) -> None:
    case = installation(tmp_path)
    with Session(case.store.engine) as db:
        key = db.scalar(select(Document.original_key))
    assert key is not None
    files(case.store.engine).delete(key)
    with pytest.raises(RecoveryError, match="stored original"):
        RecoveryService(case.settings).create(tmp_path / "missing.lgbackup", PASSWORD)
    assert not (tmp_path / "missing.lgbackup").exists()
