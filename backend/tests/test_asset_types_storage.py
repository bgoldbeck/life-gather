import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from database_support import database
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_asset_types import definition
from test_reconciliation import setup

from lifegather.assets.manual import ManualAssetCreate, ManualAssets
from lifegather.assets.type_models import AssetType, AssetTypeRevision
from lifegather.assets.type_schemas import TypeFieldSave, TypeSave
from lifegather.assets.types import AssetTypes
from lifegather.auth.store import AuthStore
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.export import RecordExport
from lifegather.memory.models import Entity
from lifegather.memory.service import MemoryError


def test_atomic_stale_typed_creation_retirement_and_unchanged_legacy_fields(
    tmp_path: Path,
) -> None:
    store, alice, _, memory, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    original = types.save(alice, definition())
    field = original["fields"][0]
    edit = {
        "type_id": original["id"],
        "expected_revision": original["revision"],
        "name": original["name"],
        "fields": [{**field, "retired": True}],
        "request_id": "retire",
    }
    current = types.save(alice, TypeSave.model_validate(edit))
    with pytest.raises(MemoryError):
        ManualAssets(store.engine).save(
            alice,
            ManualAssetCreate.model_validate(
                {
                    "name": "Must roll back",
                    "ownership_confirmed": True,
                    "request_id": "invalid",
                    "type_id": original["id"],
                    "type_revision": original["revision"],
                }
            ),
        )
    assert memory.find_entities(alice, "Must roll back") == []
    with Session(store.engine) as db:
        assert (
            db.scalar(select(Entity.id).where(Entity.name == "Must roll back")) is None
        )
    # The retired definition keeps its original stable field ID, but no new values.
    assert current["fields"][0]["id"] == field["id"]
    with pytest.raises(ValidationError):
        TypeSave(name="Invalid", request_id="reserved", fields=[{"name": "serial"}])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        TypeFieldSave(
            entity_id="x",
            type_id="x",
            field_id=field["id"],
            value="Missing",
            text="No support.",
            request_id="bad",
        )


def test_concurrent_definition_edits_and_retry_are_serialized(tmp_path: Path) -> None:
    store, alice, _, _, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    create = definition()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: types.save(alice, create), range(2)))
    assert results[0] == results[1]
    initial = results[0]

    def update(key: str) -> str:
        try:
            types.save(
                alice,
                TypeSave.model_validate(
                    {
                        "type_id": initial["id"],
                        "expected_revision": initial["revision"],
                        "name": "New name",
                        "fields": initial["fields"],
                        "request_id": key,
                    }
                ),
            )
            return "saved"
        except MemoryError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, ["one", "two"])) == ["saved", "stale"]
    with Session(store.engine) as db:
        assert len(list(db.scalars(select(AssetType)))) == 1
        assert len(list(db.scalars(select(AssetTypeRevision)))) == 2


def test_type_definitions_json_zip_and_encrypted_operator_recovery(
    tmp_path: Path,
) -> None:
    from test_recovery_bundle import PASSWORD, installation

    from lifegather.recovery.bundle import RecoveryService

    case = installation(tmp_path)
    types = AssetTypes(case.store.engine)
    template = types.save(case.alice, definition())
    raw = RecordExport(case.store.engine).download(case.alice)
    with ZipFile(
        BytesIO(
            PersonalArchive(case.store.engine, files(case.store.engine)).download(
                case.alice
            )
        )
    ) as archive:
        records = json.loads(archive.read("records.json"))
        assert records["collections"]["asset_types"][0]["id"] == template["id"]
        assert (
            records["collections"]["asset_type_fields"][0]["id"]
            == template["fields"][0]["id"]
        )
    assert template["id"].encode() in raw
    assert template["id"].encode() not in RecordExport(case.store.engine).download(
        case.bob
    )
    bundle, restored = tmp_path / "types.lgbackup", tmp_path / "restored-types"
    recovery = RecoveryService(case.settings)
    recovery.create(bundle, PASSWORD)
    url = database(restored / "data", empty=True)
    recovery.restore(bundle, restored, PASSWORD, url)
    recovered = AuthStore(url)
    assert AssetTypes(recovered.engine).get(case.alice, template["id"]) == template
    assert (
        len(AssetTypes(recovered.engine).history(case.alice, template["id"])["items"])
        == 1
    )
    recovered.engine.dispose()


def test_catalog_pages_are_private_and_defaults_are_not_overwritten(
    tmp_path: Path,
) -> None:
    store, alice, bob, _, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    custom = types.save(alice, definition())
    first = types.list(alice)
    assert first["next_cursor"] and len(first["items"]) == 5
    assert (
        types.list(alice, cursor=first["next_cursor"])["items"][0]["id"] == custom["id"]
    )
    with pytest.raises(MemoryError):
        types.list(bob, cursor=first["next_cursor"])


def test_consolidation_preserves_original_type_conflicts_and_retry_subjects(
    tmp_path: Path,
) -> None:
    from lifegather.assets.consolidation import Consolidate, ConsolidationService
    from lifegather.assets.type_schemas import TypeAssign
    from lifegather.profiles.service import ProfileCreate, ProfileService

    store, alice, _, _, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    catalog = types.list(alice)["items"]
    items = [
        ProfileService(store.engine).create(
            alice,
            ProfileCreate(
                name=f"Synthetic vehicle {index}",
                kind="vehicle",
                text="My synthetic item.",
                operation_key=str(index),
            ),
        )
        for index in range(2)
    ]
    assignments = [
        TypeAssign(
            entity_id=item.id, type_id=catalog[index]["id"], request_id=f"type-{index}"
        )
        for index, item in enumerate(items)
    ]
    for command in assignments:
        types.assign(alice, command)
    field = catalog[1]["fields"][0]
    value = TypeFieldSave(
        entity_id=items[1].id,
        type_id=catalog[1]["id"],
        field_id=field["id"],
        value="Synthetic",
        text="Synthetic",
        request_id="field",
    )
    original = types.save_field(alice, value)
    service = ConsolidationService(store.engine)
    preview = service.preview(alice, items[0].id, items[1].id)
    service.apply(
        alice,
        Consolidate(
            primary_id=items[0].id,
            secondary_id=items[1].id,
            preview_token=preview["preview_token"],
            same_item_confirmed=True,
            request_id="join",
            note="Same item confirmed.",
        ),
    )
    current = types.record(alice, items[0].id)
    assert len(current["assignments"]) == 2
    assert current["facts"][0]["id"] == original["id"]
    assert types.save_field(alice, value)["id"] == original["id"]
    assert types.assign(alice, assignments[1])["subject_id"] == items[1].id
