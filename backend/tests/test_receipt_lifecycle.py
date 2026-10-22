"""Synthetic regression across reviewed discovery, correction, recall and restore."""

from pathlib import Path

import pytest
from database_support import restore_copy
from test_automatic_receipts import automatic
from test_purchase_details import SOURCE, body
from test_receipts import extraction
from test_reconciliation import setup

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.service import AssetRead, AssetService
from lifegather.auth.store import AuthStore
from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService, SaveText, save_text
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.receipts import ReceiptService
from lifegather.reconciliation.service import ReconciliationService


def test_reviewed_receipt_unit_sale_recall_and_restore_preserve_exact_evidence(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, memory, reconcile = setup(tmp_path)
    text = SOURCE.replace("USD 49.90", "JPY 4990")
    source = save_text(
        memory, actor, SaveText(text=text, request_id="lifecycle-receipt")
    )
    receipts = ReceiptService(auth.engine)
    draft = receipts.create(actor, source.id, extraction())
    request = automatic(draft)
    accepted = receipts.review(actor, request)
    assert accepted == receipts.review(actor, request)
    assert len(reconcile.inventory(actor)) == 3
    PurchaseDetails(auth.engine).save(
        actor,
        body(
            accepted,
            currency="JPY",
            line_total="4990",
            money_quote=text.splitlines()[0],
        ),
    )
    line = accepted["result"]["lines"][0]
    old, sibling = line["asset_ids"]
    evidence = memory.ingest(
        actor, SourceInput(text="Synthetic existing replacement drill.")
    )
    target = memory.create_entity(
        actor,
        EntityInput(
            name="Existing replacement drill",
            kind="asset",
            source_id=evidence.id,
            operation_key="lifecycle-target",
        ),
    )
    actions = ActionService(auth.engine)
    move = AssetChange(
        asset_id=old,
        request_id="lifecycle-move",
        operation="reassociate",
        decision_id=line["decision_id"],
        target_asset_id=target.id,
        note="Only receipt unit 1 belongs to this existing drill.",
    )
    moved = actions.apply(actor, move)
    purchases = AssetPurchases(auth.engine)
    assert purchases.get(actor, AssetPurchasesRead(asset_id=old))["items"] == []
    target_purchase = purchases.get(actor, AssetPurchasesRead(asset_id=target.id))[
        "items"
    ][0]
    assert target_purchase["unit"] == 1 and target_purchase["quantity"] == 2
    assert target_purchase["claim"]["total_minor"] == 4990
    assert target_purchase["claim"]["line_total"] == "4990"
    assert target_purchase["claim"]["currency"] == "JPY"
    assert (
        purchases.get(actor, AssetPurchasesRead(asset_id=sibling))["items"][0]["unit"]
        == 2
    )
    sold = actions.apply(
        actor,
        AssetChange(
            asset_id=target.id,
            request_id="lifecycle-sale",
            operation="ownership",
            status="sold",
            note="I sold this synthetic replacement drill.",
        ),
    )
    expected = set([sibling, *accepted["result"]["lines"][1]["asset_ids"]])
    assert set(reconcile.inventory(actor)) == expected
    detail = AssetService(auth.engine).get(actor, AssetRead(asset_id=target.id))
    assert not detail["in_inventory"] and detail["action_head"] == sold["id"]
    assert {row["id"] for row in detail["actions"]} == {sold["id"], moved["id"]}
    assert any(row["direction"] == "incoming" for row in detail["actions"])
    plan = RecallPlan(
        query="replacement drill", entity_names=[target.name], include_connections=False
    )
    context = RecallTools(ChatService(auth.engine)).collect(actor, plan)
    recalled = [
        purchase for record in context["records"] for purchase in record["purchases"]
    ]
    assert len(recalled) == 1 and recalled[0]["claim"]["line_total"] == "4990"
    assert recalled[0]["source_id"] == source.id
    assert source.id in {row["id"] for row in context["evidence"]}
    assert RecallTools(ChatService(auth.engine)).collect(foreign, plan)["records"] == []
    with pytest.raises(MemoryError):
        AssetService(auth.engine).get(foreign, AssetRead(asset_id=target.id))
    snapshot = tmp_path / "receipt-lifecycle.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    assert set(ReconciliationService(restored.engine).inventory(actor)) == expected
    assert (
        AssetService(restored.engine).get(actor, AssetRead(asset_id=target.id))
        == detail
    )
    assert ActionService(restored.engine).apply(actor, move) == moved
    assert (
        AssetPurchases(restored.engine).get(
            actor, AssetPurchasesRead(asset_id=target.id)
        )["items"][0]
        == target_purchase
    )
    assert memory.get_source(actor, source.id).text == text
