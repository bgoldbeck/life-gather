from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_asset_actions import change
from test_mcp_http import rpc, signed_headers
from test_reconciliation import discovery
from test_unit_corrections import prepared

from lifegather.assets.actions import ActionService
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.replacements import (
    ReplacementRecord,
    ReplacementService,
    ReplacementWithdraw,
)
from lifegather.assets.service import AssetRead, AssetService
from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.service import ReconciliationService


def replacement(tmp_path: Path) -> tuple[Any, ...]:
    auth, actor, bob, memory, reconcile, _, line, target, _ = prepared(tmp_path)
    service = ReplacementService(auth.engine)
    request = ReplacementRecord(
        asset_id=line["asset_ids"][0],
        target_asset_id=target.id,
        request_id="replacement",
        note="This existing replacement drill replaced my original drill.",
        event_date="2025-01-02",
    )
    return auth, actor, bob, memory, reconcile, line, target, service, request


def test_replacement_preserves_distinct_items_receipts_and_ownership(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, line, target, service, request = replacement(
        tmp_path
    )
    inventory = reconcile.inventory(actor)
    purchases = AssetPurchases(auth.engine)
    claims = purchases.get(actor, AssetPurchasesRead(asset_id=request.asset_id))
    owned = memory.facts(actor, request.asset_id)
    result = service.change(actor, request)
    assert service.change(actor, request) == result
    assert reconcile.inventory(actor) == inventory
    assert purchases.get(actor, AssetPurchasesRead(asset_id=request.asset_id)) == claims
    assert not purchases.get(actor, AssetPurchasesRead(asset_id=target.id))["items"]
    assert reconcile.get(actor, line["id"]).asset_ids == line["asset_ids"]
    facts = memory.facts(actor, request.asset_id)
    assert {row.id for row in owned} <= {row.id for row in facts}
    relation = next(row for row in facts if row.id == result["fact_id"])
    assert relation.object_id == target.id and relation.predicate == "replaced_by"
    assert relation.status == "stated" and str(relation.valid_from) == "2025-01-02"
    assert relation.evidence == [
        {"source_id": result["source_id"], "quote": request.note}
    ]
    assert any(
        edge.id == relation.id for edge in memory.related(actor, target.id)["edges"]
    )
    incoming = AssetService(auth.engine).get(actor, AssetRead(asset_id=target.id))
    assert (
        incoming["action_head"] == ""
        and incoming["actions"][0]["operation"] == "replacement"
    )
    context = ActionService(auth.engine).source_context(actor, result["source_id"])
    assert context is not None
    assert context["target_asset_name"] == target.name


def test_withdrawal_preserves_temporal_history_and_snapshot_replay(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _, _, target, service, request = replacement(tmp_path)
    result = service.change(actor, request)
    recorded = next(
        fact
        for fact in memory.facts(actor, request.asset_id)
        if fact.id == result["fact_id"]
    )
    snapshot = tmp_path / "replacement.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    service = ReplacementService(restored.engine)
    assert service.change(actor, request) == result
    withdraw = ReplacementWithdraw(
        action_id=result["id"],
        request_id="withdraw",
        note="I chose the wrong replacement item.",
    )
    with pytest.raises(MemoryError):
        service.change(bob, withdraw)
    reversed_result = service.change(actor, withdraw)
    assert service.change(actor, withdraw) == reversed_result
    assert service.change(actor, request) == result
    memory = MemoryService(restored.engine)
    assert not any(
        edge.id == result["fact_id"]
        for edge in memory.related(actor, target.id)["edges"]
    )
    assert not any(
        fact.id == result["fact_id"] for fact in memory.facts(actor, request.asset_id)
    )
    earlier = memory.facts(actor, request.asset_id, known_at=recorded.recorded_at)
    assert any(
        fact.id == recorded.id and fact.valid_from == recorded.valid_from
        for fact in earlier
    )
    assert memory.get_source(actor, result["source_id"]).text == request.note
    assert memory.get_source(actor, reversed_result["source_id"]).text == withdraw.note
    history = AssetService(restored.engine).get(
        actor, AssetRead(asset_id=request.asset_id)
    )
    assert [action["operation"] for action in history["actions"]] == [
        "replacement_withdrawn",
        "replacement",
    ]


def test_replacement_refusals_and_concurrent_replay(tmp_path: Path) -> None:
    auth, actor, bob, memory, _, _, _, service, request = replacement(tmp_path)
    sources = memory.export_page(actor, "sources")
    with pytest.raises(MemoryError):
        service.change(bob, request)
    for fields in (
        {"target_asset_id": request.asset_id},
        {"event_date": "2999-01-01"},
        {"note": "  "},
        {"event_date": "2025-02-30"},
    ):
        with pytest.raises(ValidationError):
            service.change(actor, request.model_copy(update=fields))
    assert memory.export_page(actor, "sources") == sources
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.change(actor, request), range(2)))
    assert results[0] == results[1]
    result = results[0]
    with pytest.raises(NoteConflict):
        service.change(actor, request.model_copy(update={"note": "Different retry"}))
    with pytest.raises(NoteConflict, match="already recorded"):
        service.change(
            actor,
            request.model_copy(
                update={"request_id": "duplicate", "expected_action_id": result["id"]}
            ),
        )
    ActionService(auth.engine).apply(
        actor, change(request.asset_id, expected_action_id=result["id"])
    )
    sources = memory.export_page(actor, "sources")
    with pytest.raises(NoteConflict, match="Later corrections"):
        service.change(
            actor,
            ReplacementWithdraw(
                action_id=result["id"],
                request_id="withdraw-stale",
                note="Refuse stale withdrawal",
            ),
        )
    assert memory.export_page(actor, "sources") == sources


def test_replacement_transaction_failure_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, actor, _, memory, _, _, _, service, request = replacement(tmp_path)
    sources = memory.export_page(actor, "sources")
    facts = memory.export_page(actor, "facts")
    audit = service.memory._audit

    def fail(*args: Any) -> None:
        if args[2] == "asset_replacement":
            raise MemoryError("Synthetic failure after fact and action writes")
        audit(*args)

    monkeypatch.setattr(service.memory, "_audit", fail)
    with pytest.raises(MemoryError, match="Synthetic"):
        service.change(actor, request)
    assert memory.export_page(actor, "sources") == sources
    assert memory.export_page(actor, "facts") == facts


def test_replacement_keeps_explicit_negative_ownership_and_refuses_foreign_targets(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile, _, target, service, request = replacement(
        tmp_path
    )
    actions = ActionService(auth.engine)
    sold = actions.apply(actor, change(request.asset_id))
    actions.apply(actor, change(target.id, request_id="returned", status="returned"))
    inventory = reconcile.inventory(actor)
    request = request.model_copy(update={"expected_action_id": sold["id"]})
    foreign_source = memory.ingest(bob, SourceInput(text="Synthetic private target"))
    foreign = memory.create_entity(
        bob,
        EntityInput(
            name="Foreign asset",
            kind="asset",
            source_id=foreign_source.id,
            operation_key="foreign",
        ),
    )
    sources = memory.export_page(actor, "sources")
    with pytest.raises(MemoryError):
        service.change(
            actor, request.model_copy(update={"target_asset_id": foreign.id})
        )
    assert memory.export_page(actor, "sources") == sources
    service.change(actor, request)
    assert reconcile.inventory(actor) == inventory
    for item in (request.asset_id, target.id):
        assert any(
            fact.predicate == "owned" and fact.value is False
            for fact in memory.facts(actor, item)
        )


def test_withdrawal_cannot_overwrite_a_manually_corrected_relationship(
    tmp_path: Path,
) -> None:
    _, actor, _, memory, _, _, target, service, request = replacement(tmp_path)
    result = service.change(actor, request)
    memory.correct_fact(
        actor,
        result["fact_id"],
        FactInput(
            subject_id=request.asset_id,
            predicate="replaced_by",
            object_id=target.id,
            status="unknown",
            source_id=result["source_id"],
            quote=request.note,
            operation_key="manual-uncertainty",
        ),
    )
    before = memory.export_page(actor, "facts")
    with pytest.raises(NoteConflict, match="already changed"):
        service.change(
            actor,
            ReplacementWithdraw(
                action_id=result["id"],
                request_id="withdraw",
                note="Must not overwrite the manual correction",
            ),
        )
    assert memory.export_page(actor, "facts") == before


def test_withdrawal_failure_and_competing_requests_preserve_atomic_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, _, memory, _, _, _, service, request = replacement(tmp_path)

    def record(index: int) -> str:
        try:
            return str(
                service.change(
                    actor,
                    request.model_copy(update={"request_id": f"competing-{index}"}),
                )["id"]
            )
        except NoteConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(record, range(2)))
    assert results.count("conflict") == 1
    identifier = next(value for value in results if value != "conflict")
    before = memory.export_page(actor, "facts")
    sources = memory.export_page(actor, "sources")

    def fail(*args: Any) -> None:
        raise MemoryError("Synthetic withdrawal failure")

    monkeypatch.setattr(service.memory, "_audit", fail)
    with pytest.raises(MemoryError, match="withdrawal"):
        service.change(
            actor,
            ReplacementWithdraw(
                action_id=identifier, request_id="withdraw", note="Synthetic withdrawal"
            ),
        )
    assert memory.export_page(actor, "facts") == before
    assert memory.export_page(actor, "sources") == sources
    assert (
        AssetService(auth.engine).get(actor, AssetRead(asset_id=request.asset_id))[
            "action_head"
        ]
        == identifier
    )


def test_replacement_private_http_mcp_contract() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "replacement-owner")
        foreign_headers, _ = signed_headers(app, "replacement-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        original = ReconciliationService(engine).discover(
            actor, discovery(memory, actor)
        )
        target = memory.create_entity(
            actor,
            EntityInput(
                name="New existing item",
                kind="asset",
                source_id=discovery(memory, actor, key="target").source_id,
                operation_key="target",
            ),
        )
        request = ReplacementRecord(
            asset_id=original.asset_ids[0],
            target_asset_id=target.id,
            request_id="http-replacement",
            note="This distinct item replaced the original.",
        ).model_dump()
        path = "/api/assets/replacements/"
        assert client.post(path + "record", json=request).status_code == 401
        assert (
            client.post(
                path + "record", headers={"Cookie": headers["Cookie"]}, json=request
            ).status_code
            == 403
        )
        assert (
            client.post(
                path + "record", headers=foreign_headers, json=request
            ).status_code
            == 400
        )
        result = rpc(client, headers, "asset_replacement_record", request).json()[
            "result"
        ]["structuredContent"]
        assert result["event_date"] is None
        assert (
            client.post(path + "record", headers=headers, json=request).json() == result
        )
        withdraw = {
            "action_id": result["id"],
            "request_id": "http-withdraw",
            "note": "Withdraw my statement",
        }
        assert rpc(
            client, foreign_headers, "asset_replacement_withdraw", withdraw
        ).json()["result"]["isError"]
        assert (
            client.post(
                path + "withdraw", headers={"Cookie": headers["Cookie"]}, json=withdraw
            ).status_code
            == 403
        )
        result = rpc(client, headers, "asset_replacement_withdraw", withdraw).json()[
            "result"
        ]["structuredContent"]
        assert (
            client.post(path + "withdraw", headers=headers, json=withdraw).json()
            == result
        )
