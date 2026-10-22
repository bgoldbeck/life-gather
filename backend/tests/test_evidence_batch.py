import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import restore_copy
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_asset_actions import change
from test_mcp_http import rpc, signed_headers
from test_reconciliation import discovery, setup
from test_unit_corrections import prepared

from lifegather.assets.actions import ActionService
from lifegather.assets.batch import (
    EvidenceBatchService,
    EvidenceMove,
    EvidenceMovePreview,
    EvidenceRestore,
)
from lifegather.assets.models import AssetAction
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.service import AssetRead, AssetService
from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Audit
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.models import Decision
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


def batch(tmp_path: Path) -> tuple[Any, ...]:
    auth, actor, bob, memory, reconcile, receipt, line, target, single = prepared(
        tmp_path
    )
    source_id = line["asset_ids"][0]
    other = receipt["result"]["lines"][1]
    reconcile.resolve(actor, other["id"], other["decision_id"], asset_ids=[source_id])
    service = EvidenceBatchService(auth.engine)
    preview = service.preview(
        actor, EvidenceMovePreview(asset_id=source_id, target_asset_id=target.id)
    )
    move = EvidenceMove(
        asset_id=source_id,
        target_asset_id=target.id,
        preview_token=preview["preview_token"],
        request_id="batch",
        note="These two synthetic discovery sources belong to the destination.",
    )
    return (
        auth,
        actor,
        bob,
        memory,
        reconcile,
        receipt,
        line,
        target,
        single,
        service,
        preview,
        move,
    )


@pytest.mark.parametrize("clock_offset", [0, -1_000_000])
def test_batch_history_never_precedes_its_decisions(
    tmp_path: Path, clock_offset: int
) -> None:
    auth, actor, _, memory, reconcile, _, _, target, _, service, preview, move = batch(
        tmp_path
    )
    anchor = max(
        reconcile.get(actor, entry["observation_id"]).recorded_at
        for entry in preview["entries"]
    )
    service.memory.clock = lambda: anchor + clock_offset
    service.reconcile.memory.clock = lambda: anchor + clock_offset
    moved = service.move(actor, move)

    def check(result: dict[str, Any], key: str, active_asset: str) -> int:
        with Session(auth.engine) as db:
            row = db.scalar(select(AssetAction).where(AssetAction.id == result["id"]))
            assert row is not None
            times = list(
                db.scalars(
                    select(Decision.recorded_at).where(
                        Decision.id.in_([entry[key] for entry in result["entries"]])
                    )
                )
            )
            assert len(times) == 2
            assert row.recorded_at >= max(times)
            source = memory.get_source(actor, row.source_id)
            assert source.recorded_at == row.recorded_at
            assert (
                db.scalar(
                    select(Audit.recorded_at).where(
                        Audit.user_id == actor.id,
                        Audit.target_id == row.id,
                        Audit.operation == "asset_" + row.operation,
                    )
                )
                == row.recorded_at
            )
            assert any(
                fact.predicate == "owned" and fact.value is True
                for fact in memory.facts(actor, active_asset, known_at=row.recorded_at)
            )
            return row.recorded_at

    moved_at = check(moved, "moved_decision_id", target.id)
    restore = EvidenceRestore(
        action_id=moved["id"], request_id="clock-restore", note="Restore both mappings."
    )
    restored = service.restore(actor, restore)
    restored_at = check(restored, "restored_decision_id", move.asset_id)
    assert restored_at > moved_at
    assert not memory.facts(actor, target.id, known_at=restored_at)
    assert memory.facts(actor, target.id, known_at=moved_at)
    snapshot = tmp_path / "chronology.jsonl"
    operator_snapshot(auth.engine, snapshot)
    recovered = AuthStore(restore_copy(snapshot))
    recovered.migrate()
    replay = EvidenceBatchService(recovered.engine)
    assert replay.move(actor, move) == moved
    assert replay.restore(actor, restore) == restored


def test_atomic_multi_source_move_reverse_replay_and_backup(tmp_path: Path) -> None:
    (
        auth,
        actor,
        _,
        memory,
        reconcile,
        receipt,
        line,
        target,
        _,
        service,
        preview,
        move,
    ) = batch(tmp_path)
    assert len(preview["entries"]) == 2
    original_source = memory.get_source(actor, receipt["source_id"])
    fact = memory.assert_fact(
        actor,
        FactInput(
            subject_id=move.asset_id,
            predicate="color",
            value="red",
            status="stated",
            source_id=original_source.id,
            quote=original_source.text,
            operation_key="manual",
        ),
    )
    result = service.move(actor, move)
    assert service.move(actor, move) == result
    assert reconcile.get(actor, line["id"]).asset_ids == [
        target.id,
        line["asset_ids"][1],
    ]
    assert memory.facts(actor, move.asset_id)[0].subject_id == move.asset_id
    assert any(row.id == fact.id for row in memory.facts(actor, move.asset_id))
    claims = AssetPurchases(auth.engine).get(
        actor, AssetPurchasesRead(asset_id=target.id)
    )["items"]
    assert len(claims) == 2 and any(
        row["claim"] and row["claim"]["total_minor"] == 4990 for row in claims
    )
    target_detail = AssetService(auth.engine).get(actor, AssetRead(asset_id=target.id))
    assert (
        target_detail["action_head"] == ""
        and target_detail["actions"][0]["id"] == result["id"]
    )
    assert target_detail["actions"][0]["result"]["association_count"] == 2
    assert "entries" not in target_detail["actions"][0]["result"]
    snapshot = tmp_path / "batch.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    service = EvidenceBatchService(restored.engine)
    assert service.move(actor, move) == result
    undo = EvidenceRestore(
        action_id=result["id"],
        request_id="reverse",
        note="Restore the earlier mappings.",
    )
    reversed_result = service.restore(actor, undo)
    assert service.restore(actor, undo) == reversed_result
    assert service.move(actor, move) == result
    assert (
        ReconciliationService(restored.engine).get(actor, line["id"]).asset_ids
        == line["asset_ids"]
    )
    assert (
        MemoryService(restored.engine).get_source(actor, receipt["source_id"])
        == original_source
    )


def test_preview_staleness_duplicate_unit_and_owner_refusals(tmp_path: Path) -> None:
    auth, actor, bob, memory, _, _, line, _, single, service, _, move = batch(tmp_path)
    sources = memory.export_page(actor, "sources")
    for owner, data in (
        (bob, move),
        (actor, move.model_copy(update={"target_asset_id": line["asset_ids"][1]})),
    ):
        with pytest.raises(MemoryError):
            service.move(owner, data)
    assert memory.export_page(actor, "sources") == sources
    ActionService(auth.engine).apply(actor, single)
    sources = memory.export_page(actor, "sources")
    with pytest.raises(NoteConflict):
        service.move(actor, move)
    assert memory.export_page(actor, "sources") == sources


def test_batch_concurrency_request_conflicts_and_atomic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, actor, _, memory, reconcile, _, line, _, _, service, _, move = batch(tmp_path)
    before = reconcile.get(actor, line["id"])
    sources = memory.export_page(actor, "sources")
    audit = service.memory._audit

    def fail(*args: Any) -> None:
        if args[2] == "asset_batch_move":
            raise MemoryError("Synthetic failure after all decisions")
        audit(*args)

    monkeypatch.setattr(service.memory, "_audit", fail)
    with pytest.raises(MemoryError, match="Synthetic"):
        service.move(actor, move)
    assert reconcile.get(actor, line["id"]) == before
    assert memory.export_page(actor, "sources") == sources
    monkeypatch.setattr(service.memory, "_audit", audit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.move(actor, move), range(2)))
    assert results[0] == results[1]
    with pytest.raises(NoteConflict, match="request conflict"):
        service.move(actor, move.model_copy(update={"note": "Different retry"}))


@pytest.mark.parametrize("change_item", ["source", "target", "evidence"])
def test_restore_refuses_later_changes_without_partial_writes(
    tmp_path: Path, change_item: str
) -> None:
    auth, actor, _, memory, reconcile, _, line, target, _, service, _, move = batch(
        tmp_path
    )
    result = service.move(actor, move)
    if change_item == "evidence":
        current = reconcile.get(actor, line["id"])
        reconcile.resolve(
            actor, line["id"], current.decision_id, asset_ids=line["asset_ids"]
        )
    else:
        ActionService(auth.engine).apply(
            actor,
            change(
                move.asset_id if change_item == "source" else target.id,
                expected_action_id=result["id"] if change_item == "source" else "",
            ),
        )
    sources = memory.export_page(actor, "sources")
    facts = memory.export_page(actor, "facts")
    with pytest.raises(NoteConflict):
        service.restore(
            actor,
            EvidenceRestore(
                action_id=result["id"],
                request_id="restore",
                note="Must refuse stale reversal.",
            ),
        )
    assert memory.export_page(actor, "sources") == sources
    assert memory.export_page(actor, "facts") == facts


def test_batch_bound_refuses_partial_movement(tmp_path: Path) -> None:
    _, actor, _, memory, reconcile, _, _, _, _, service, _, move = batch(tmp_path)
    for index in range(4):
        incoming = reconcile.discover(
            actor, discovery(memory, actor, key=f"extra{index}", order=f"extra{index}")
        )
        reconcile.resolve(
            actor, incoming.id, incoming.decision_id, asset_ids=[move.asset_id]
        )
    with pytest.raises(MemoryError, match="one and five"):
        service.preview(
            actor,
            EvidenceMovePreview(
                asset_id=move.asset_id, target_asset_id=move.target_asset_id
            ),
        )


def test_maximum_unicode_payload_and_unit_mappings_fit_tool_budget(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    text = "🧰" * 2000
    name = "🧰" * 200
    source = memory.ingest(actor, SourceInput(text=text))
    target = memory.create_entity(
        actor,
        EntityInput(
            name=name, kind="asset", source_id=source.id, operation_key="unicode-target"
        ),
    )
    originals = []
    common = ""
    for index in range(5):
        incoming = reconcile.discover(
            actor,
            DiscoveryInput(
                source_id=source.id,
                item_key=f"unicode-{index}",
                name=name,
                quantity=20,
                kind="purchase",
                quote=text,
            ),
        )
        created = reconcile.resolve(
            actor, incoming.id, incoming.decision_id, asset_ids=None
        )
        if not common:
            common = created.asset_ids[0]
        else:
            created = reconcile.resolve(
                actor,
                incoming.id,
                created.decision_id,
                asset_ids=[common, *created.asset_ids[1:]],
            )
        originals.append((incoming.id, created.asset_ids))
    service = EvidenceBatchService(auth.engine)
    preview = service.preview(
        actor, EvidenceMovePreview(asset_id=common, target_asset_id=target.id)
    )
    assert all(
        entry["quote_truncated"] and len(entry["quote"]) == 400
        for entry in preview["entries"]
    )
    move = EvidenceMove(
        asset_id=common,
        target_asset_id=target.id,
        preview_token=preview["preview_token"],
        request_id="unicode-move",
        note="Explicit synthetic unicode batch",
    )
    result = service.move(actor, move)
    restored = service.restore(
        actor,
        EvidenceRestore(
            action_id=result["id"],
            request_id="unicode-restore",
            note="Restore every original mapping",
        ),
    )
    for value in (preview, result, restored):
        assert len(json.dumps(value, ensure_ascii=False).encode()) < 32768
    for observation_id, asset_ids in originals:
        assert reconcile.get(actor, observation_id).asset_ids == asset_ids


def test_batch_http_mcp_auth_csrf_and_private_contract() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "batch-owner")
        foreign_headers, _ = signed_headers(app, "batch-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        reconcile = ReconciliationService(engine)
        incoming = reconcile.discover(actor, discovery(memory, actor))
        target = memory.create_entity(
            actor,
            EntityInput(
                name="Target",
                kind="asset",
                source_id=discovery(memory, actor, key="target-source").source_id,
                operation_key="target",
            ),
        )
        pair = {"asset_id": incoming.asset_ids[0], "target_asset_id": target.id}
        path = "/api/assets/evidence/"
        assert client.post(path + "preview", json=pair).status_code == 401
        assert (
            client.post(
                path + "preview", headers=foreign_headers, json=pair
            ).status_code
            == 400
        )
        preview = client.post(path + "preview", headers=headers, json=pair).json()
        assert (
            rpc(client, headers, "asset_evidence_preview", pair).json()["result"][
                "structuredContent"
            ]
            == preview
        )
        request = {
            **pair,
            "preview_token": preview["preview_token"],
            "request_id": "http-batch",
            "note": "Explicit synthetic choice",
        }
        assert (
            client.post(
                path + "move", headers={"Cookie": headers["Cookie"]}, json=request
            ).status_code
            == 403
        )
        result = rpc(client, headers, "asset_evidence_move", request).json()["result"][
            "structuredContent"
        ]
        assert (
            client.post(path + "move", headers=headers, json=request).json() == result
        )
        reverse = {
            "action_id": result["id"],
            "request_id": "http-reverse",
            "note": "Restore mappings",
        }
        assert rpc(client, foreign_headers, "asset_evidence_restore", reverse).json()[
            "result"
        ]["isError"]
        assert (
            client.post(
                path + "restore", headers={"Cookie": headers["Cookie"]}, json=reverse
            ).status_code
            == 403
        )
        reversed_result = rpc(
            client, headers, "asset_evidence_restore", reverse
        ).json()["result"]["structuredContent"]
        assert (
            client.post(path + "restore", headers=headers, json=reverse).json()
            == reversed_result
        )
