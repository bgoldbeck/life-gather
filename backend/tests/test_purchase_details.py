from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_mcp_http import rpc, signed_headers
from test_receipts import TEXT, choices, extraction
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.purchase_details import (
    DetailRead,
    DetailSave,
    PurchaseDetails,
)
from lifegather.reconciliation.receipt_models import ReceiptDetail
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService

MONEY = "Acme Drill Qty: 2; Line total: USD 49.90"
WHEN = "Purchase date: 2026-10-18"
SOURCE = MONEY + "\nAcme Saw Qty: 1\n" + WHEN


def accepted(engine: Any, actor: Any, text: str = SOURCE) -> dict[str, Any]:
    memory = MemoryService(engine)
    source = save_text(memory, actor, SaveText(text=text, request_id="receipt"))
    service = ReceiptService(engine)
    draft = service.create(actor, source.id, extraction())
    return service.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="confirm",
            choices=choices(service, actor, draft),
        ),
    )


def body(receipt: dict[str, Any], **changes: Any) -> DetailSave:
    return DetailSave.model_validate(
        {
            "receipt_id": receipt["id"],
            "index": 0,
            "request_id": "detail",
            "line_total": "49.90",
            "money_quote": MONEY,
            "purchase_date": "2026-10-18",
            "date_quote": WHEN,
            "reason": "Copied exact receipt passages",
            **changes,
        }
    )


def test_exact_total_concurrent_replay_history_clear_and_restore(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    data = body(receipt)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: service.save(actor, data), range(3)))
    assert results[0] == results[1] == results[2]
    assert results[0]["total_minor"] == 4990 and results[0]["line_total"] == "49.90"
    assert results[0]["currency"] == "USD"
    read = DetailRead(receipt_id=receipt["id"], index=0)
    page = service.get(actor, read)
    assert page["quantity"] == 2 and len(page["items"]) == 1
    with pytest.raises(MemoryError):
        service.get(bob, read)
    with pytest.raises(MemoryError):
        service.save(bob, data)
    with pytest.raises(MemoryError, match="conflict"):
        service.save(actor, body(receipt, line_total="49.91"))
    with pytest.raises(MemoryError, match="changed"):
        service.save(actor, body(receipt, request_id="stale"))
    cleared = service.save(
        actor,
        body(
            receipt,
            request_id="clear",
            expected_head=results[0]["id"],
            line_total=None,
            money_quote=None,
            purchase_date=None,
            date_quote=None,
            reason="Withdraw unsupported purchase details",
        ),
    )
    assert cleared["total_minor"] is None and cleared["purchase_date"] is None
    assert service.get(actor, read)["items"] == [cleared, results[0]]
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(ReceiptDetail)))) == 2
    snapshot = tmp_path / "snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert PurchaseDetails(restored.engine).get(actor, read) == service.get(actor, read)
    restored.engine.dispose()
    auth.engine.dispose()


@pytest.mark.parametrize(
    "changes",
    [
        {"line_total": "49.91"},
        {"money_quote": "Line total: USD 49.90"},
        {"money_quote": MONEY.replace("USD", "$ ")},
        {"purchase_date": "2026-02-30"},
        {"purchase_date": "2026-10-19"},
        {"date_quote": "2026-10-18"},
        {"line_total": None},
        {"purchase_date": None},
        {"reason": "   "},
    ],
)
def test_unsupported_claims_do_not_write(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    with pytest.raises(MemoryError):
        service.save(actor, body(receipt, **changes))
    assert (
        service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))["items"] == []
    )
    auth.engine.dispose()


@pytest.mark.parametrize(
    "value", [49.90, "1.999", "-1.00", "1e2", "1,000.00", "1000000000.00"]
)
def test_money_input_is_bounded_exact_decimal_string(value: Any) -> None:
    with pytest.raises(ValidationError):
        DetailSave(
            receipt_id="r", index=0, request_id="r", reason="test", line_total=value
        )


def test_source_correction_blocks_new_revisions_but_preserves_read_and_replay(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    data = body(receipt)
    result = service.save(actor, data)
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=receipt["source_id"],
            text="Corrected source",
            request_id="correct",
        ),
    )
    assert service.save(actor, data) == result
    with pytest.raises(MemoryError):
        service.save(
            actor, body(receipt, request_id="later", expected_head=result["id"])
        )
    page = service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))
    assert not page["can_edit"] and page["current"] == result
    auth.engine.dispose()


def test_detail_history_pagination_and_purchase_only_guard(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    head = None
    for i in range(7):
        result = service.save(
            actor,
            body(
                receipt,
                request_id=str(i),
                expected_head=head,
                reason=f"Synthetic revision {i}",
            ),
        )
        head = result["id"]
    first = service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))
    second = service.get(
        actor,
        DetailRead(
            receipt_id=receipt["id"], index=0, before_revision=first["next_revision"]
        ),
    )
    assert [r["revision"] for r in first["items"] + second["items"]] == [
        7,
        6,
        5,
        4,
        3,
        2,
        1,
    ]
    assert second["current_head"] == head and second["next_revision"] is None
    source = save_text(
        MemoryService(auth.engine), actor, SaveText(text=TEXT, request_id="possession")
    )
    receipts = ReceiptService(auth.engine)
    draft = receipts.create(actor, source.id, extraction())
    selected = choices(receipts, actor, draft)
    for choice in selected:
        choice.fields.kind = "possession"
        from lifegather.reconciliation.receipts import ReceiptPreview

        choice.check = receipts.preview(
            actor,
            ReceiptPreview(
                receipt_id=draft["id"], index=choice.index, fields=choice.fields
            ),
        )["check"]
    receipts.review(
        actor,
        ReceiptReview(receipt_id=draft["id"], request_id="possess", choices=selected),
    )
    with pytest.raises(MemoryError, match="purchased"):
        service.get(actor, DetailRead(receipt_id=draft["id"], index=0))
    auth.engine.dispose()


def test_detail_http_mcp_owner_and_csrf_boundaries() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        receipt = accepted(app.state.auth_store.engine, actor)
        data = body(receipt).model_dump()
        assert client.post("/api/receipts/details/save", json=data).status_code == 401
        assert (
            client.post(
                "/api/receipts/details/save",
                headers={"Cookie": alice["Cookie"]},
                json=data,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/receipts/details/save", headers=bob, json=data
            ).status_code
            == 400
        )
        response = client.post("/api/receipts/details/save", headers=alice, json=data)
        assert response.status_code == 200, response.text
        result = rpc(client, alice, "receipt_details_save", data).json()["result"]
        assert not result.get("isError")
        query = {"receipt_id": receipt["id"], "index": 0}
        assert (
            not rpc(client, alice, "receipt_details_get", query)
            .json()["result"]
            .get("isError")
        )
        assert (
            rpc(client, bob, "receipt_details_get", query)
            .json()["result"]
            .get("isError")
        )
        assert (
            client.post("/api/receipts/details/read", headers=alice, json=query).json()[
                "current"
            ]["total_minor"]
            == 4990
        )


@pytest.mark.parametrize(
    "amount,cents", [("0.10", 10), ("0.00", 0), ("999999999.99", 99999999999)]
)
def test_minor_units_zero_and_upper_bound(
    tmp_path: Path, amount: str, cents: int
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor, SOURCE.replace("49.90", amount))
    result = PurchaseDetails(auth.engine).save(
        actor,
        body(receipt, line_total=amount, money_quote=MONEY.replace("49.90", amount)),
    )
    assert result["total_minor"] == cents and result["line_total"] == amount
    auth.engine.dispose()


def test_deleted_pdf_preserves_purchase_history_without_new_writes(
    tmp_path: Path,
) -> None:
    from test_documents import synthetic_pdf

    from lifegather.documents.service import (
        DocumentDelete,
        DocumentService,
        DocumentText,
    )

    auth, actor, _, _, _ = setup(tmp_path)
    docs = DocumentService(auth.engine)
    doc = docs.upload(actor, synthetic_pdf(), "synthetic.pdf")
    doc = docs.save_text(
        actor,
        DocumentText(
            document_id=doc["id"], text=SOURCE, expected_updated_at=doc["updated_at"]
        ),
    )
    receipts = ReceiptService(auth.engine)
    draft = receipts.create(actor, doc["source_id"], extraction())
    receipt = receipts.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="confirm",
            choices=choices(receipts, actor, draft),
        ),
    )
    service = PurchaseDetails(auth.engine)
    result = service.save(actor, body(receipt))
    docs.delete(
        actor,
        DocumentDelete(document_id=doc["id"], expected_updated_at=doc["updated_at"]),
    )
    page = service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))
    assert page["current"] == result and not page["can_edit"]
    with pytest.raises(MemoryError, match="deleted"):
        service.save(
            actor, body(receipt, request_id="later", expected_head=result["id"])
        )
    auth.engine.dispose()


def test_upgrade_preserves_confirmed_receipt(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather

    auth = AuthStore(tmp_path / "legacy.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with auth.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0014_receipt_proposals")
    actor = auth.login("legacy", "legacy@example.test", "Synthetic", now=1).user
    receipt = accepted(auth.engine, actor)
    auth.migrate()
    assert ReceiptService(auth.engine).get(actor, receipt["id"]) == receipt
    result = PurchaseDetails(auth.engine).save(actor, body(receipt))
    assert result["total_minor"] == 4990
    auth.engine.dispose()


def test_purchase_read_suggests_exact_source_claims_without_writes(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    read = DetailRead(receipt_id=receipt["id"], index=0)
    page = service.get(actor, read)
    assert page["suggestions"] == {
        "line_total": "49.90",
        "currency": "USD",
        "money_quote": MONEY,
        "purchase_date": "2026-10-18",
        "date_quote": WHEN,
    }
    assert page["items"] == []
    service.save(actor, body(receipt, **page["suggestions"]))
    with pytest.raises(MemoryError):
        service.get(bob, read)
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=receipt["source_id"], text="Corrected", request_id="changed"
        ),
    )
    assert service.get(actor, read)["suggestions"] is None
    auth.engine.dispose()


@pytest.mark.parametrize(
    "suffix",
    [
        "\nPurchase date: 2026-10-19",
        "\nPurchase date: 2026-02-30",
    ],
)
def test_ambiguous_or_invalid_dates_are_not_suggested(
    tmp_path: Path, suffix: str
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor, SOURCE + suffix)
    page = PurchaseDetails(auth.engine).get(
        actor, DetailRead(receipt_id=receipt["id"], index=0)
    )
    assert page["suggestions"]["purchase_date"] is None
    assert page["suggestions"]["date_quote"] is None
    auth.engine.dispose()


@pytest.mark.parametrize(
    "currency,amount,minor",
    [
        ("EUR", "49.90", 4990),
        ("GBP", "0.10", 10),
        ("CAD", "49.90", 4990),
        ("AUD", "0.00", 0),
        ("JPY", "4990", 4990),
    ],
)
def test_explicit_currency_claims_round_trip_without_conversion(
    tmp_path: Path,
    currency: str,
    amount: str,
    minor: int,
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    text = SOURCE.replace("USD 49.90", f"{currency} {amount}")
    receipt = accepted(auth.engine, actor, text)
    service = PurchaseDetails(auth.engine)
    page = service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))
    assert page["suggestions"]["currency"] == currency
    result = service.save(
        actor,
        body(
            receipt,
            currency=currency,
            line_total=amount,
            money_quote=MONEY.replace("USD 49.90", f"{currency} {amount}"),
        ),
    )
    assert result["currency"] == currency
    assert result["line_total"] == amount and result["total_minor"] == minor
    assert (
        service.save(
            actor,
            body(
                receipt,
                currency=currency,
                line_total=amount,
                money_quote=MONEY.replace("USD 49.90", f"{currency} {amount}"),
            ),
        )
        == result
    )
    auth.engine.dispose()


def test_currency_change_requires_matching_source_quote(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    with pytest.raises(MemoryError):
        PurchaseDetails(auth.engine).save(actor, body(receipt, currency="EUR"))
    auth.engine.dispose()


def test_currency_migration_preserves_usd_history_and_legacy_replay(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather
    from lifegather.memory.service import fingerprint

    auth = AuthStore(tmp_path / "legacy-currency.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with auth.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0015_receipt_details")
    actor = auth.login("legacy", "legacy@example.test", "Synthetic", now=1).user
    receipt = accepted(auth.engine, actor)
    service = PurchaseDetails(auth.engine)
    data = body(receipt)
    saved = service.save(actor, data)
    old_payload = data.model_dump(exclude={"currency"})
    with Session(auth.engine) as db:
        stored = db.get(ReceiptDetail, saved["id"])
        assert stored is not None and stored.fingerprint == fingerprint(old_payload)
    auth.migrate()
    assert service.save(actor, data) == saved
    page = service.get(actor, DetailRead(receipt_id=receipt["id"], index=0))
    assert page["items"] == [saved]
    auth.engine.dispose()


@pytest.mark.parametrize(
    "currency,amount",
    [
        ("JPY", "1.00"),
        ("EUR", "1"),
        ("USD", "1.999"),
        ("JPY", "100000000000"),
        ("CHF", "1.00"),
    ],
)
def test_rejects_unsupported_precision_or_currency(currency: str, amount: str) -> None:
    with pytest.raises(ValidationError):
        DetailSave.model_validate(
            dict(
                receipt_id="r",
                index=0,
                request_id="x",
                reason="test",
                currency=currency,
                line_total=amount,
            )
        )


@pytest.mark.parametrize(
    "passage",
    [
        "Line total: EUR 1e2",
        "Line total: USD -1.00",
        "Line total: JPY 1.00",
        "Line total: CHF 1.00",
        "Line total: $ 1.00",
        "Line total: EUR 1.000",
        "Line total: EUR 1.00-",
        "Line total: USD 1.00; Line total: EUR 1.00",
    ],
)
def test_ambiguous_amounts_are_never_suggested(passage: str) -> None:
    suggested = PurchaseDetails.suggestions(
        "Synthetic item " + passage, "Synthetic item"
    )
    assert suggested["line_total"] is None and suggested["currency"] is None


def test_downgrade_refuses_to_discard_non_usd_claims(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather

    auth, actor, _, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor, SOURCE.replace("USD", "EUR"))
    PurchaseDetails(auth.engine).save(
        actor, body(receipt, currency="EUR", money_quote=MONEY.replace("USD", "EUR"))
    )
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with pytest.raises(RuntimeError, match="data loss"):
        with auth.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0015_receipt_details")
    assert (
        PurchaseDetails(auth.engine).get(
            actor, DetailRead(receipt_id=receipt["id"], index=0)
        )["current"]["currency"]
        == "EUR"
    )
    auth.engine.dispose()
