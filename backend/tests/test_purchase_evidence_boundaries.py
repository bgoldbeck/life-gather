from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import restore_copy
from pydantic import ValidationError
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.purchases.schemas import EvidenceSave, EvidenceWithdraw
from lifegather.purchases.service import PurchaseEvidenceService


def test_exact_order_id_is_not_a_prefix_and_amount_date_must_be_supported(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    service = PurchaseEvidenceService(auth.engine)
    source = memory.ingest(
        actor, SourceInput(text="Synthetic Store order P100; USD 12.34; 2025-01-02")
    )
    base = dict(
        source_id=source.id,
        role="order",
        retailer="Synthetic Store",
        account_scope="mine",
        order_id="P100",
        quote=source.text,
        reason="Synthetic",
        request_id="first",
    )
    with pytest.raises(MemoryError):
        service.save(actor, EvidenceSave.model_validate({**base, "order_id": "P1"}))
    for fields in (
        {"quote": "invented"},
        {"amount": "12.35", "money_quote": "USD 12.34"},
        {"occurred_on": "2025-01-03", "date_quote": "2025-01-02"},
    ):
        with pytest.raises(MemoryError):
            service.save(actor, EvidenceSave.model_validate({**base, **fields}))
    for amount in ("12.345", "-1.00", "1e2"):
        with pytest.raises(ValidationError):
            EvidenceSave.model_validate(
                {**base, "amount": amount, "money_quote": "USD " + amount}
            )
    valid = service.save(
        actor,
        EvidenceSave.model_validate(
            {
                **base,
                "amount": "12.34",
                "money_quote": "USD 12.34",
                "occurred_on": "2025-01-02",
                "date_quote": "2025-01-02",
            }
        ),
    )
    assert valid["amount_minor"] == 1234 and valid["occurred_on"] == "2025-01-02"
    auth.engine.dispose()


def test_conflict_and_stale_source_history_are_not_silently_overwritten(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    service = PurchaseEvidenceService(auth.engine)
    rows = []
    for index, amount in enumerate(("10.00", "11.00")):
        source = memory.ingest(
            actor,
            SourceInput(
                text=f"Synthetic Store order A1 USD {amount}",
                source_type="conversation",
                namespace="chat-memory",
                external_id=str(index),
            ),
        )
        rows.append(
            service.save(
                actor,
                EvidenceSave(
                    source_id=source.id,
                    role="receipt",
                    retailer="Synthetic Store",
                    account_scope="mine",
                    order_id="A1",
                    quote=source.text,
                    amount=amount,
                    money_quote="USD " + amount,
                    reason="Synthetic",
                    request_id=str(index),
                ),
            )
        )
    assert service.get(actor, rows[0]["purchase_id"])["conflicting_totals"] is True
    correction = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=rows[1]["source_id"],
            text="Synthetic corrected note",
            request_id="correct",
        ),
    )
    assert correction is not None
    group = service.get(actor, rows[0]["purchase_id"])
    assert not group["conflicting_totals"]
    assert any(not item["source_current"] for item in group["items"])
    assert not service.source_context(actor, rows[1]["source_id"])["can_attach"]
    withdrawn = service.withdraw(
        actor,
        EvidenceWithdraw(
            source_id=rows[1]["source_id"],
            expected_head=rows[1]["id"],
            reason="Original corrected",
            request_id="withdraw",
        ),
    )
    assert withdrawn["state"] == "withdrawn"
    assert len(service.history(actor, rows[1]["source_id"])["items"]) == 2
    auth.engine.dispose()


def test_concurrent_replay_restore_and_explicit_payment_link(tmp_path: Path) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    service = PurchaseEvidenceService(auth.engine)
    source = memory.ingest(actor, SourceInput(text="Synthetic Store order A1"))
    data = EvidenceSave(
        source_id=source.id,
        role="order",
        retailer="Synthetic Store",
        account_scope="mine",
        order_id="A1",
        quote=source.text,
        reason="Synthetic",
        request_id="same",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: service.save(actor, data), range(2)))
    assert rows[0]["id"] == rows[1]["id"]
    paid = memory.ingest(actor, SourceInput(text="Synthetic card charge USD 5.00"))
    payment = EvidenceSave(
        source_id=paid.id,
        purchase_id=rows[0]["purchase_id"],
        role="payment",
        quote=paid.text,
        amount="5.00",
        money_quote="USD 5.00",
        reason="Explicitly reviewed partial charge",
        request_id="payment",
    )
    service.save(actor, payment)
    with pytest.raises(MemoryError):
        service.save(bob, payment)
    with pytest.raises(MemoryError):
        service.save(actor, data.model_copy(update={"role": "receipt"}))
    snapshot = tmp_path / "purchases.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    copied = PurchaseEvidenceService(restored.engine)
    assert copied.get(actor, rows[0]["purchase_id"]) == service.get(
        actor, rows[0]["purchase_id"]
    )
    assert copied.get(actor, rows[0]["purchase_id"])["amounts_are_not_summed"]
    restored.engine.dispose()
    auth.engine.dispose()


def test_purchase_http_mcp_ownership_csrf_and_body_limit() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app
    from lifegather.memory.service import MemoryService

    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "purchase-alice")
        bob, _ = signed_headers(app, "purchase-bob")
        source = MemoryService(app.state.auth_store.engine).ingest(
            actor, SourceInput(text="Synthetic Store order P1")
        )
        body: dict[str, Any] = dict(
            source_id=source.id,
            role="order",
            retailer="Synthetic Store",
            account_scope="mine",
            order_id="P1",
            quote=source.text,
            reason="Synthetic",
            request_id="first",
        )
        assert client.get("/api/purchases").status_code == 401
        assert (
            client.post(
                "/api/purchases/evidence",
                headers={"Cookie": alice["Cookie"]},
                json=body,
            ).status_code
            == 403
        )
        created = rpc(client, alice, "purchase_evidence_save", body).json()
        assert not created["result"].get("isError"), created
        item = client.get("/api/purchases", headers=alice).json()["items"][0]
        assert (
            client.get("/api/purchases/" + item["id"], headers=bob).status_code == 400
        )
        assert (
            client.get("/api/purchases/sources/" + source.id, headers=bob).status_code
            == 400
        )
        assert rpc(client, bob, "purchase_get", {"purchase_id": item["id"]}).json()[
            "result"
        ]["isError"]
        assert (
            client.post(
                "/api/purchases/evidence", headers=alice, content=b"x" * 32769
            ).status_code
            == 413
        )
        assert client.get("/api/purchases", headers=bob).json()["items"] == []
