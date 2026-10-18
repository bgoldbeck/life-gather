from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_mcp_http import rpc, signed_headers
from test_purchase_details import SOURCE, accepted, body
from test_receipts import choices, extraction
from test_reconciliation import setup

from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService


def assets(receipt: dict[str, Any], index: int = 0) -> list[str]:
    return [str(value) for value in receipt["result"]["lines"][index]["asset_ids"]]


def test_asset_purchase_latest_claims_unknowns_and_private_ownership(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = AssetPurchases(auth.engine)
    query = AssetPurchasesRead(asset_id=assets(receipt)[0])
    initial = service.get(actor, query)
    assert initial["items"][0]["claim"] is None
    with pytest.raises(MemoryError):
        service.get(bob, query)
    details = PurchaseDetails(auth.engine)
    claim = details.save(actor, body(receipt))
    for unit, asset in enumerate(assets(receipt)):
        item = service.get(actor, AssetPurchasesRead(asset_id=asset))["items"][0]
        assert item["unit"] == unit + 1 and item["quantity"] == 2
        assert (
            item["claim"]["total_minor"] == 4990
            and item["claim"]["line_total"] == "49.90"
        )
        assert item["source_id"] == receipt["source_id"] and item["source_current"]
    assert (
        service.get(actor, AssetPurchasesRead(asset_id=assets(receipt, 1)[0]))["items"][
            0
        ]["claim"]
        is None
    )
    cleared = details.save(
        actor,
        body(
            receipt,
            expected_head=claim["id"],
            request_id="withdraw",
            line_total=None,
            money_quote=None,
            purchase_date=None,
            date_quote=None,
            reason="Withdraw unsupported claim",
        ),
    )
    item = service.get(actor, query)["items"][0]
    assert item["claim"] == cleared and item["claim"]["line_total"] is None
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=receipt["source_id"],
            text="Corrected source",
            request_id="correct",
        ),
    )
    assert not service.get(actor, query)["items"][0]["source_current"]
    auth.engine.dispose()


def test_purchase_records_follow_reassociation_dismissal_and_undo(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    source = save_text(memory, actor, SaveText(text=SOURCE, request_id="other"))
    receipts = ReceiptService(auth.engine)
    draft = receipts.create(actor, source.id, extraction())
    second = receipts.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="other-confirm",
            choices=choices(receipts, actor, draft),
        ),
    )
    PurchaseDetails(auth.engine).save(actor, body(receipt))
    service = AssetPurchases(auth.engine)
    original = receipt["result"]["lines"][0]
    moved = reconcile.resolve(
        actor, original["id"], original["decision_id"], asset_ids=assets(second)
    )
    assert not service.get(actor, AssetPurchasesRead(asset_id=assets(receipt)[0]))[
        "items"
    ]
    assert (
        len(service.get(actor, AssetPurchasesRead(asset_id=assets(second)[0]))["items"])
        == 2
    )
    restored = reconcile.undo(actor, moved.decision_id)
    assert (
        service.get(actor, AssetPurchasesRead(asset_id=assets(receipt)[0]))["items"][0][
            "claim"
        ]["total_minor"]
        == 4990
    )
    dismissed = reconcile.dismiss(actor, restored.id, restored.decision_id)
    assert not service.get(actor, AssetPurchasesRead(asset_id=assets(receipt)[0]))[
        "items"
    ]
    reconcile.undo(actor, dismissed.decision_id)
    assert service.get(actor, AssetPurchasesRead(asset_id=assets(receipt)[0]))["items"]
    auth.engine.dispose()


def test_asset_receipt_pages_are_bounded_and_do_not_repeat(tmp_path: Path) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    first = accepted(auth.engine, actor)
    receipts = ReceiptService(auth.engine)
    for i in range(6):
        source = save_text(
            memory, actor, SaveText(text=SOURCE, request_id=f"source-{i}")
        )
        draft = receipts.create(actor, source.id, extraction())
        selected = choices(receipts, actor, draft)
        for choice in selected:
            choice.action = "link"
            choice.asset_ids = assets(first, choice.index)
        receipts.review(
            actor,
            ReceiptReview(
                receipt_id=draft["id"], request_id=f"review-{i}", choices=selected
            ),
        )
    service = AssetPurchases(auth.engine)
    query = AssetPurchasesRead(asset_id=assets(first)[0])
    page1 = service.get(actor, query)
    page2 = service.get(
        actor, query.model_copy(update={"cursor": page1["next_cursor"]})
    )
    assert (
        len(page1["items"]) == 5
        and len(page2["items"]) == 2
        and page2["next_cursor"] is None
    )
    assert len({item["key"] for item in page1["items"] + page2["items"]}) == 7
    auth.engine.dispose()


def test_asset_purchase_http_and_mcp_are_private_read_only() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        receipt = accepted(app.state.auth_store.engine, actor)
        PurchaseDetails(app.state.auth_store.engine).save(actor, body(receipt))
        asset = assets(receipt)[0]
        url = f"/api/assets/{asset}/purchases"
        assert client.get(url).status_code == 401
        assert client.get(url, headers=bob).status_code == 400
        response = client.get(url, headers=alice)
        assert (
            response.status_code == 200
            and response.json()["items"][0]["claim"]["total_minor"] == 4990
        )
        assert client.get(url + "?limit=6", headers=alice).status_code == 422
        assert client.get(url + "?cursor=bad", headers=alice).status_code == 422
        assert (
            not rpc(client, alice, "asset_purchases", {"asset_id": asset})
            .json()["result"]
            .get("isError")
        )
        assert (
            rpc(client, bob, "asset_purchases", {"asset_id": asset})
            .json()["result"]
            .get("isError")
        )
