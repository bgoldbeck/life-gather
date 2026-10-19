from pathlib import Path

import pytest
from test_reconciliation import discovery, setup

from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.purchases.schemas import EvidenceSave, EvidenceWithdraw
from lifegather.purchases.service import PurchaseEvidenceService


def test_four_sources_reuse_canonical_purchase_without_duplicate_items(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    original = reconcile.discover(actor, discovery(memory, actor))
    purchases = PurchaseEvidenceService(auth.engine)
    saved = []
    for role in ("order", "receipt", "shipment", "payment"):
        text = f"Home Depot order A100: synthetic {role}. USD 349.00 on 2025-01-02"
        source = memory.ingest(
            actor,
            SourceInput(
                text=text, source_type="email", namespace="synthetic", external_id=role
            ),
        )
        value = EvidenceSave(
            source_id=source.id,
            role=role,
            retailer="Home Depot",
            account_scope="mine",
            order_id="A100",
            quote=text,
            amount="349.00" if role != "shipment" else None,
            currency="USD",
            money_quote="USD 349.00" if role != "shipment" else None,
            reason="Synthetic review",
            request_id=role,
        )
        saved.append(purchases.save(actor, value))
        assert purchases.save(actor, value) == saved[-1]
    assert len({row["purchase_id"] for row in saved}) == 1
    page = purchases.list(actor)
    assert len(page["items"]) == 1
    group = purchases.get(actor, saved[0]["purchase_id"])
    assert len(group["items"]) == 4 and group["conflicting_totals"] is False
    assert group["linked_asset_ids"] == original.asset_ids
    assert len(reconcile.inventory(actor)) == 1
    assert purchases.list(bob)["items"] == []
    with pytest.raises(MemoryError):
        purchases.get(bob, saved[0]["purchase_id"])
    auth.engine.dispose()


def test_correction_move_withdraw_history_and_payment_cannot_create(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    purchases = PurchaseEvidenceService(auth.engine)
    text = "Synthetic Shop order P1; Synthetic Shop order P2; USD 12.34"
    source = memory.ingest(actor, SourceInput(text=text))
    base = EvidenceSave(
        source_id=source.id,
        role="payment",
        retailer="Synthetic Shop",
        account_scope="mine",
        order_id="P1",
        quote=text,
        reason="Synthetic",
        request_id="payment",
    )
    with pytest.raises(MemoryError, match="payment|Payment"):
        purchases.save(actor, base)
    first = purchases.save(
        actor, base.model_copy(update={"role": "order", "request_id": "first"})
    )
    with pytest.raises(MemoryError):
        purchases.save(
            actor, base.model_copy(update={"role": "receipt", "request_id": "stale"})
        )
    moved = purchases.save(
        actor,
        base.model_copy(
            update={
                "role": "receipt",
                "order_id": "P2",
                "expected_head": first["id"],
                "request_id": "move",
            }
        ),
    )
    assert moved["purchase_id"] != first["purchase_id"]
    withdrawn = purchases.withdraw(
        actor,
        EvidenceWithdraw(
            source_id=source.id,
            expected_head=moved["id"],
            reason="Wrong association",
            request_id="withdraw",
        ),
    )
    assert withdrawn["state"] == "withdrawn"
    assert purchases.source_context(actor, source.id)["head"]["id"] == withdrawn["id"]
    assert len(purchases.history(actor, source.id)["items"]) == 3
    assert purchases.get(actor, first["purchase_id"])["items"] == []
    assert purchases.get(actor, moved["purchase_id"])["items"] == []
    assert reconcile.inventory(actor) == []
    auth.engine.dispose()


def test_evidence_first_is_reused_by_order_line_asset_reconciliation(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    service = PurchaseEvidenceService(auth.engine)
    source = memory.ingest(
        actor, SourceInput(text="Home Depot order A100 confirmation")
    )
    created = service.save(
        actor,
        EvidenceSave(
            source_id=source.id,
            role="order",
            retailer="Home Depot",
            account_scope="mine",
            order_id="A100",
            quote=source.text,
            reason="Synthetic",
            request_id="order",
        ),
    )
    first = reconcile.discover(actor, discovery(memory, actor, key="first"))
    second = reconcile.discover(actor, discovery(memory, actor, key="second"))
    assert second.outcome == "enrich" and first.asset_ids == second.asset_ids
    assert len(service.list(actor)["items"]) == 1
    assert (
        service.get(actor, created["purchase_id"])["linked_asset_ids"]
        == first.asset_ids
    )
    auth.engine.dispose()
