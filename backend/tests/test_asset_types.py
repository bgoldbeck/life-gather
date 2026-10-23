import json
from pathlib import Path
from typing import Any

import pytest
from test_reconciliation import setup

from lifegather.assets.manual import ManualAssetCreate, ManualAssets
from lifegather.assets.type_schemas import TypeAssign, TypeFieldSave, TypeSave
from lifegather.assets.types import AssetTypes
from lifegather.memory.export import RecordExport
from lifegather.memory.service import MemoryError


def definition(**changes: Any) -> TypeSave:
    return TypeSave.model_validate(
        dict(
            name="Garden equipment",
            description="My tools",
            fields=[{"name": "Battery family"}],
            request_id="type-create",
            **changes,
        )
    )


def test_defaults_are_private_editable_and_create_no_assets(tmp_path: Path) -> None:
    store, alice, bob, memory, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    rows = types.list(alice)["items"]
    assert [row["name"] for row in rows] == [
        "Vehicle",
        "Appliance",
        "Electronics",
        "Furniture",
        "Tools & Equipment",
    ]
    assert not memory.find_entities(alice, "Vehicle")
    assert not (
        {row["id"] for row in rows} & {row["id"] for row in types.list(bob)["items"]}
    )
    with pytest.raises(MemoryError):
        types.get(bob, rows[0]["id"])
    vehicle = rows[0]
    bob_revision = types.list(bob)["items"][0]["revision"]
    updated = types.save(
        alice,
        TypeSave.model_validate(
            {
                **{
                    key: vehicle[key]
                    for key in ("name", "description", "fields", "retired")
                },
                "type_id": vehicle["id"],
                "expected_revision": vehicle["revision"],
                "request_id": "vehicle-update",
            }
        ),
    )
    assert updated["id"] == vehicle["id"]
    assert types.get(bob, types.list(bob)["items"][0]["id"])["revision"] == bob_revision


def test_type_revisions_retry_staleness_retirement_and_field_identity(
    tmp_path: Path,
) -> None:
    store, alice, bob, _, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    original = types.save(alice, definition())
    field = original["fields"][0]
    edit = TypeSave.model_validate(
        {
            "type_id": original["id"],
            "expected_revision": original["revision"],
            "request_id": "edit",
            "name": "Garden tools",
            "fields": [
                {**field, "name": "Battery system", "retired": True},
                {"name": "Blade length"},
            ],
        }
    )
    updated = types.save(alice, edit)
    assert types.save(alice, edit) == updated
    assert types.save(alice, definition()) == original
    assert updated["fields"][0]["id"] == field["id"]
    with pytest.raises(MemoryError):
        types.save(alice, edit.model_copy(update={"request_id": "stale"}))
    with pytest.raises(MemoryError):
        types.save(bob, edit)
    with pytest.raises(MemoryError):
        types.save(
            alice,
            edit.model_copy(
                update={
                    "request_id": "drop",
                    "expected_revision": updated["revision"],
                    "fields": [],
                }
            ),
        )
    assert len(types.history(alice, original["id"])["items"]) == 2
    raw = RecordExport(store.engine).download(alice)
    exported = json.loads(raw)
    assert exported["format"] == "lifegather-records/6"
    assert len(exported["collections"]["asset_type_revisions"]) == 2
    assert original["id"].encode() not in RecordExport(store.engine).download(bob)


def test_typed_manual_entry_later_field_and_sourced_correction(tmp_path: Path) -> None:
    store, alice, bob, memory, _ = setup(tmp_path)
    types = AssetTypes(store.engine)
    template = types.save(alice, definition())
    field = template["fields"][0]
    data = ManualAssetCreate.model_validate(
        {
            "name": "Synthetic garden tool",
            "ownership_confirmed": True,
            "request_id": "asset",
            "type_id": template["id"],
            "type_revision": template["revision"],
            "type_values": [
                {
                    "field_id": field["id"],
                    "value": "18 V",
                    "text": "My battery family is 18 V.",
                }
            ],
        }
    )
    saved = ManualAssets(store.engine).save(alice, data)
    assert ManualAssets(store.engine).save(alice, data) == saved
    asset_id = saved["asset"]["id"]
    record = types.record(alice, asset_id)
    assert record["assignments"][0]["value"] == template["id"]
    fact = record["facts"][0]
    assert fact["value"] == "18 V" and fact["label"] == "Battery family"
    with pytest.raises(MemoryError):
        types.record(bob, asset_id)
    update = types.save(
        alice,
        TypeSave.model_validate(
            {
                "type_id": template["id"],
                "expected_revision": template["revision"],
                "request_id": "new-field",
                "name": template["name"],
                "fields": [field, {"name": "Blade length"}],
            }
        ),
    )
    assert len(types.record(alice, asset_id)["facts"]) == 1
    assert len(update["fields"]) == 2
    change = TypeFieldSave(
        entity_id=asset_id,
        type_id=template["id"],
        field_id=field["id"],
        value="20 V",
        text="Correction: my battery family is 20 V.",
        request_id="correct",
        replaces_id=fact["id"],
    )
    revised = types.save_field(alice, change)
    assert types.save_field(alice, change) == revised
    history = types.record(alice, asset_id, history=True)
    assert len(history["facts"]) == 2
    assert memory.get_source(alice, fact["evidence"][0]["source_id"]).text.endswith(
        "My battery family is 18 V."
    )
    with pytest.raises(MemoryError):
        types.assign(
            bob,
            TypeAssign(
                entity_id=asset_id, type_id=template["id"], request_id="foreign"
            ),
        )
