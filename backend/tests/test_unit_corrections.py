from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_asset_actions import change
from test_mcp_http import rpc, signed_headers
from test_purchase_details import accepted, body
from test_reconciliation import setup

from lifegather.assets.actions import ActionService
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.service import AssetRead, AssetService
from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.service import ReconciliationService


def prepared(tmp_path: Path) -> tuple[Any, ...]:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    PurchaseDetails(auth.engine).save(actor, body(receipt))
    line = receipt["result"]["lines"][0]
    source = memory.ingest(actor, SourceInput(text="Synthetic existing replacement."))
    target = memory.create_entity(
        actor,
        EntityInput(
            name="Existing replacement",
            kind="asset",
            source_id=source.id,
            operation_key="target",
        ),
    )
    request = change(
        line["asset_ids"][0],
        request_id="unit-move",
        operation="reassociate",
        status=None,
        event_date=None,
        decision_id=line["decision_id"],
        target_asset_id=target.id,
        note="Receipt unit 1 belongs to this existing item.",
    )
    return auth, actor, bob, memory, reconcile, receipt, line, target, request


def test_move_one_receipt_unit_and_reverse_without_changing_other_units(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, receipt, line, target, request = prepared(
        tmp_path
    )
    actions = ActionService(auth.engine)
    old = list(line["asset_ids"])
    moved = actions.apply(actor, request)
    assert moved["decision"]["asset_ids"] == [target.id, old[1]]
    assert moved["unit"] == 1 and moved["quantity"] == 2
    assert actions.apply(actor, request) == moved
    purchases = AssetPurchases(auth.engine)
    assert not purchases.get(actor, AssetPurchasesRead(asset_id=old[0]))["items"]
    assert (
        purchases.get(actor, AssetPurchasesRead(asset_id=old[1]))["items"][0]["unit"]
        == 2
    )
    assert (
        purchases.get(actor, AssetPurchasesRead(asset_id=target.id))["items"][0]["unit"]
        == 1
    )
    for identifier in (target.id, old[1]):
        claim = purchases.get(actor, AssetPurchasesRead(asset_id=identifier))["items"][
            0
        ]["claim"]
        assert claim["total_minor"] == 4990 and claim["currency"] == "USD"
    reverse = actions.apply(
        actor,
        request.model_copy(
            update={
                "asset_id": target.id,
                "target_asset_id": old[0],
                "request_id": "reverse",
                "decision_id": moved["decision"]["decision_id"],
                "note": "Restore unit 1 association.",
            }
        ),
    )
    assert reverse["decision"]["asset_ids"] == old
    assert actions.apply(actor, request) == moved  # historical replay remains exact
    history = reconcile.history(actor, line["id"])
    assert len(history) == 3  # confirmed discovery, correction, reversal
    assert memory.get_source(actor, receipt["source_id"]).text
    assert AssetService(auth.engine).get(actor, AssetRead(asset_id=old[1]))[
        "in_inventory"
    ]


def test_unit_refusals_rollback_and_competing_sibling_corrections(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _, _, line, target, request = prepared(tmp_path)
    actions = ActionService(auth.engine)
    before = memory.export_page(actor, "sources")
    for changes in (
        {"target_asset_id": line["asset_ids"][1]},
        {"target_asset_id": None},
        {"operation": "undo", "target_asset_id": None},
    ):
        with pytest.raises(MemoryError):
            actions.apply(actor, request.model_copy(update=changes))
        assert memory.export_page(actor, "sources") == before
    with pytest.raises(MemoryError):
        actions.apply(bob, request)

    def move(index: int) -> str:
        data = request.model_copy(
            update={
                "asset_id": line["asset_ids"][index],
                "request_id": f"concurrent-{index}",
            }
        )
        try:
            return str(actions.apply(actor, data)["id"])
        except NoteConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, range(2)))
    assert results.count("conflict") == 1
    current = ReconciliationService(auth.engine).get(actor, line["id"])
    assert len(set(current.asset_ids)) == 2 and target.id in current.asset_ids


def test_unit_transaction_failure_and_snapshot_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, _, memory, reconcile, _, line, _, request = prepared(tmp_path)
    actions = ActionService(auth.engine)
    sources = memory.export_page(actor, "sources")
    initial = reconcile.get(actor, line["id"])
    audit = actions.memory._audit

    def fail(db: Any, owner: Any, operation: str, identifier: str, now: int) -> None:
        if operation == "asset_reassociate":
            raise MemoryError("Synthetic failure after replacement decision")
        audit(db, owner, operation, identifier, now)

    monkeypatch.setattr(actions.memory, "_audit", fail)
    with pytest.raises(MemoryError, match="Synthetic failure"):
        actions.apply(actor, request)
    assert reconcile.get(actor, line["id"]) == initial
    assert memory.export_page(actor, "sources") == sources
    monkeypatch.setattr(actions.memory, "_audit", audit)
    result = actions.apply(actor, request)
    snapshot = tmp_path / "unit-snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert ActionService(restored.engine).apply(actor, request) == result
    assert (
        ReconciliationService(restored.engine).get(actor, line["id"]).asset_ids
        == result["decision"]["asset_ids"]
    )


def test_unit_http_and_mcp_private_shared_contract() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "unit-owner")
        foreign_headers, foreign = signed_headers(app, "unit-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        receipt = accepted(engine, actor)
        line = receipt["result"]["lines"][0]
        source = memory.ingest(actor, SourceInput(text="Synthetic target source"))
        target = memory.create_entity(
            actor,
            EntityInput(
                name="Target",
                kind="asset",
                source_id=source.id,
                operation_key="unit-target",
            ),
        )
        foreign_source = memory.ingest(
            foreign, SourceInput(text="Private foreign source")
        )
        foreign_target = memory.create_entity(
            foreign,
            EntityInput(
                name="Private target",
                kind="asset",
                source_id=foreign_source.id,
                operation_key="foreign-target",
            ),
        )
        request = change(
            line["asset_ids"][1],
            request_id="unit-http",
            operation="reassociate",
            status=None,
            event_date=None,
            decision_id=line["decision_id"],
            target_asset_id=target.id,
            note="Only the second receipt unit belongs here.",
        ).model_dump()
        path = "/api/assets/actions"
        assert client.post(path, json=request).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": headers["Cookie"]}, json=request
            ).status_code
            == 403
        )
        assert (
            client.post(path, headers=foreign_headers, json=request).status_code == 400
        )
        assert (
            client.post(
                path,
                headers=headers,
                json={**request, "target_asset_id": foreign_target.id},
            ).status_code
            == 400
        )
        result = rpc(client, headers, "asset_change", request).json()["result"][
            "structuredContent"
        ]
        assert result["unit"] == 2
        assert result["decision"]["asset_ids"] == [line["asset_ids"][0], target.id]
        assert client.post(path, headers=headers, json=request).json() == result
        assert (
            client.post(
                path, headers=headers, json={**request, "request_id": "stale"}
            ).status_code
            == 409
        )
