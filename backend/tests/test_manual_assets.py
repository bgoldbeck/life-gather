from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_reconciliation import setup

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.manual import ManualAssetCreate, ManualAssetFields, ManualAssets
from lifegather.assets.service import AssetList, AssetService
from lifegather.memory.history import FieldHistory, FieldHistoryRead
from lifegather.memory.models import Audit, Episode
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.reconciliation.models import Observation
from lifegather.reconciliation.schemas import DiscoveryInput


def fields(**changes: object) -> ManualAssetFields:
    return ManualAssetFields.model_validate(
        dict(
            {
                "name": "Synthetic trimmer",
                "manufacturer": "Acme",
                "model": "T1",
                "serial": "S1",
                "notes": "A manually entered item.",
                "ownership_confirmed": True,
            },
            **changes,
        )
    )


def test_manual_entry_is_stated_sourced_private_and_reconciles_future_sources(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    service = ManualAssets(auth.engine)
    draft = fields()
    assert service.preview(actor, draft)["candidates"] == []
    data = ManualAssetCreate(**draft.model_dump(), request_id="create")
    saved = service.save(actor, data)
    assert saved == service.save(actor, data)
    asset_id = saved["asset"]["id"]
    assert (
        AssetService(auth.engine).list(actor, AssetList())["items"][0]["id"] == asset_id
    )
    assert AssetService(auth.engine).list(bob, AssetList())["items"] == []
    item = FieldHistory(auth.engine).get(
        actor, FieldHistoryRead(entity_id=asset_id, field="owned")
    )["items"][0]
    assert item["status"] == "stated" and item["origin"]["method"] == "manual_entry"
    assert (
        "Notes:\nA manually entered item."
        in memory.get_source(actor, saved["source_id"]).text
    )
    source = memory.ingest(
        actor,
        SourceInput(text="Acme T1 S1 Synthetic trimmer"),
    )
    result = reconcile.discover(
        actor,
        DiscoveryInput(
            source_id=source.id,
            item_key="later",
            quantity=1,
            name=draft.name,
            manufacturer="Acme",
            model="T1",
            serial="S1",
            kind="purchase",
            quote=source.text,
        ),
    )
    assert result.asset_ids == [asset_id] and result.outcome == "enrich"
    assert len(reconcile.inventory(actor)) == 1
    auth.engine.dispose()


def test_saved_replay_never_reasserts_sold_ownership_and_conflicts_roll_back(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    service = ManualAssets(auth.engine)
    data = ManualAssetCreate(**fields().model_dump(), request_id="initial")
    saved = service.save(actor, data)
    identifier = saved["asset"]["id"]
    ActionService(auth.engine).apply(
        actor,
        AssetChange(
            asset_id=identifier,
            request_id="sold",
            operation="ownership",
            status="sold",
            note="I sold this item",
        ),
    )
    assert service.save(actor, data) == saved
    assert identifier not in service.reconcile.inventory(actor)
    check = service.preview(actor, fields())
    assert check["candidates"][0]["can_link"] is False
    with pytest.raises(MemoryError):
        service.save(
            actor,
            ManualAssetCreate(
                **fields().model_dump(),
                request_id="reacquire",
                action="link",
                asset_id=identifier,
                candidate_ids=[identifier],
            ),
        )
    changed = ManualAssetCreate(
        **fields(notes="Changed notes").model_dump(), request_id="initial"
    )
    with pytest.raises(MemoryError):
        service.save(actor, changed)
    assert memory.get_source(actor, saved["source_id"]).text.endswith(
        "Target: new item"
    )
    auth.engine.dispose()


def test_manual_http_and_mcp_are_owner_scoped_and_refuse_forged_origins() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        headers, _ = signed_headers(app, "manual-alice")
        bob, _ = signed_headers(app, "manual-bob")
        payload = ManualAssetCreate(
            **fields().model_dump(), request_id="api"
        ).model_dump()
        assert client.post("/api/assets/manual", json=payload).status_code == 401
        assert (
            client.post(
                "/api/assets/manual",
                json=payload,
                headers={**headers, "X-CSRF-Token": "wrong"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/assets/manual",
                json={**payload, "origin": {"method": "ai_inference"}},
                headers=headers,
            ).status_code
            == 422
        )
        response = client.post("/api/assets/manual", json=payload, headers=headers)
        assert response.status_code == 200
        identifier = response.json()["asset"]["id"]
        assert client.get("/api/assets", headers=bob).json()["items"] == []
        assert (
            not rpc(client, headers, "asset_manual_save", payload)
            .json()["result"]
            .get("isError")
        )
        preview = rpc(
            client, bob, "asset_manual_preview", fields().model_dump()
        ).json()["result"]["structuredContent"]
        assert preview["candidates"] == []
        assert identifier in client.get("/api/assets", headers=headers).text


def test_concurrent_manual_retries_and_identity_undo_preserve_the_declaration(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, reconcile = setup(tmp_path)
    service = ManualAssets(auth.engine)
    data = ManualAssetCreate(**fields().model_dump(), request_id="concurrent")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.save(actor, data), range(2)))
    assert results[0] == results[1]
    with Session(auth.engine) as db:
        observation = db.scalar(
            select(Observation).where(Observation.source_id == results[0]["source_id"])
        )
        assert observation is not None
        identifier = observation.id
    initial = reconcile.get(actor, identifier)
    undone = reconcile.undo(actor, initial.decision_id)
    restored = reconcile.resolve(
        actor, identifier, undone.decision_id, asset_ids=[results[0]["asset"]["id"]]
    )
    assert restored.asset_ids == initial.asset_ids
    history = FieldHistory(auth.engine).get(
        actor, FieldHistoryRead(entity_id=initial.asset_ids[0], field="owned")
    )
    assert all(item["status"] == "stated" for item in history["items"])
    assert len(reconcile.inventory(actor)) == 1
    auth.engine.dispose()


def test_names_require_explicit_choice_and_serials_block_duplicate_creation(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    service = ManualAssets(auth.engine)
    first = service.save(
        actor, ManualAssetCreate(**fields().model_dump(), request_id="first")
    )
    draft = fields(serial=None)
    preview = service.preview(actor, draft)
    candidates = [row["id"] for row in preview["candidates"]]
    assert candidates == [first["asset"]["id"]]
    with pytest.raises(MemoryError):
        service.save(actor, ManualAssetCreate(**draft.model_dump(), request_id="stale"))
    second = service.save(
        actor,
        ManualAssetCreate(
            **draft.model_dump(), request_id="separate", candidate_ids=candidates
        ),
    )
    assert second["asset"]["id"] != first["asset"]["id"]
    exact = service.preview(actor, fields())
    ids = [row["id"] for row in exact["candidates"]]
    with pytest.raises(MemoryError):
        service.save(
            actor,
            ManualAssetCreate(
                **fields().model_dump(), request_id="serial-dupe", candidate_ids=ids
            ),
        )
    linked = service.save(
        actor,
        ManualAssetCreate(
            **fields().model_dump(),
            request_id="link",
            action="link",
            asset_id=first["asset"]["id"],
            candidate_ids=ids,
        ),
    )
    assert linked["asset"]["id"] == first["asset"]["id"] and not linked["created"]
    with pytest.raises(MemoryError):
        service.save(
            bob,
            ManualAssetCreate(
                **draft.model_dump(),
                request_id="foreign",
                action="link",
                asset_id=first["asset"]["id"],
                candidate_ids=candidates,
            ),
        )
    with Session(auth.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Episode)
                .where(Episode.external_id.in_(["stale", "serial-dupe", "foreign"]))
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.operation == "manual_asset_saved")
            )
            == 3
        )
    auth.engine.dispose()
