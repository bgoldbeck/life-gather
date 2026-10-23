from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from test_mcp_http import rpc, signed_headers
from test_receipts import extraction
from test_reconciliation import setup

from lifegather.assets.service import AssetList, AssetService
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.receipts import (
    ReceiptChoice,
    ReceiptExtraction,
    ReceiptFields,
    ReceiptReview,
    ReceiptService,
)
from lifegather.reconciliation.schemas import DiscoveryInput

pytestmark = pytest.mark.usefixtures("configured_database")

TEXT = "Acme Drill Qty: 2\nAcme Saw Qty: 1"


def draft(engine: Any, actor: Any, memory: Any) -> tuple[Any, Any]:
    source = save_text(memory, actor, SaveText(text=TEXT, request_id="auto-receipt"))
    service = ReceiptService(engine)
    return service, service.create(actor, source.id, extraction())


def automatic(row: Any, **changes: Any) -> ReceiptReview:
    return ReceiptReview.model_validate(
        {
            "receipt_id": row["id"],
            "request_id": "auto",
            "choices": [
                dict(index=i, fields={**item, "kind": "purchase"}, action="auto")
                for i, item in enumerate(row["items"])
            ],
            **changes,
        }
    )


def test_clear_receipt_units_atomic_concurrent_replay(tmp_path: Path) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    service, row = draft(auth.engine, actor, memory)
    request = automatic(row)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: service.review(actor, request), range(3)))
    assert results[0] == results[1] == results[2]
    assert results[0]["state"] == "accepted"
    lines = results[0]["result"]["lines"]
    assert [line["automatic_outcome"] for line in lines] == ["create", "create"]
    assert len(set(asset for line in lines for asset in line["asset_ids"])) == 3
    assert len(reconcile.inventory(actor)) == 3


def test_one_ambiguous_line_leaves_entire_receipt_pending_without_writes(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    source = memory.ingest(actor, SourceInput(text="I own an Acme Saw."))
    prior = reconcile.discover(
        actor,
        DiscoveryInput(
            source_id=source.id,
            item_key="saw",
            name="Saw",
            manufacturer="Acme",
            kind="possession",
            quantity=1,
            quote=source.text,
        ),
    )
    service, row = draft(auth.engine, actor, memory)
    tables: tuple[Literal["sources", "entities", "facts", "audit"], ...] = (
        "sources",
        "entities",
        "facts",
        "audit",
    )
    before = {name: memory.export_page(actor, name) for name in tables}
    result = service.review(actor, automatic(row))
    assert result["state"] == "proposed" and result["automatic_outcome"] == "review"
    assert any(
        c["index"] == 1 and c["candidates"][0]["id"] == prior.asset_ids[0]
        for c in result["automatic_checks"]
    )
    assert len(reconcile.inventory(actor)) == 1
    assert all(
        memory.export_page(actor, name) == value for name, value in before.items()
    )
    assert service.get(actor, row["id"])["result"] == {}


def test_automatic_receipt_still_requires_reviewed_ownership_and_exact_source(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    service, row = draft(auth.engine, actor, memory)
    request = automatic(row)
    bad = request.model_copy(
        update={
            "choices": [
                ReceiptChoice(
                    index=i, fields=ReceiptFields.model_validate(item), action="auto"
                )
                for i, item in enumerate(row["items"])
            ]
        }
    )
    with pytest.raises(MemoryError):
        service.review(actor, bad)
    with pytest.raises(MemoryError):
        service.review(bob, request)
    invalid = request.choices[0].model_copy(
        update={
            "fields": request.choices[0].fields.model_copy(
                update={"quote": "Invented quote"}
            )
        }
    )
    with pytest.raises(MemoryError):
        service.review(
            actor, request.model_copy(update={"choices": [invalid, request.choices[1]]})
        )
    assert service.get(actor, row["id"])["state"] == "proposed"


@pytest.mark.parametrize("sold", [False, True])
def test_serial_enrichment_or_sold_identity_stays_pending(
    tmp_path: Path, sold: bool
) -> None:
    from lifegather.assets.actions import ActionService, AssetChange

    auth, actor, _, memory, reconcile = setup(tmp_path)
    text = "Acme Drill serial S1"
    source = memory.ingest(actor, SourceInput(text=text))
    prior = reconcile.discover(
        actor,
        DiscoveryInput(
            source_id=source.id,
            item_key="original",
            name="Drill",
            manufacturer="Acme",
            serial="S1",
            kind="purchase",
            quantity=1,
            quote=text,
        ),
    )
    if sold:
        ActionService(auth.engine).apply(
            actor,
            AssetChange(
                asset_id=prior.asset_ids[0],
                request_id="sold",
                operation="ownership",
                status="sold",
                note="Synthetic item was sold.",
            ),
        )
    source = save_text(memory, actor, SaveText(text=text, request_id="receipt-serial"))
    fields = ReceiptFields(
        name="Drill",
        manufacturer="Acme",
        model=None,
        serial="S1",
        kind="mention",
        quote=text,
        quantity=1,
        quantity_quote=None,
    )
    service = ReceiptService(auth.engine)
    row = service.create(
        actor,
        source.id,
        ReceiptExtraction(items=[fields], explanation="Synthetic serial receipt"),
    )
    result = service.review(actor, automatic(row))
    if sold:
        assert result["state"] == "proposed" and result["automatic_outcome"] == "review"
        assert AssetService(auth.engine).list(actor, AssetList())["items"] == []
    else:
        assert result["result"]["lines"][0]["automatic_outcome"] == "enrich"
        assert result["result"]["lines"][0]["asset_ids"] == prior.asset_ids
        assert len(reconcile.inventory(actor)) == 1


def test_cross_line_identity_change_rolls_back_and_stale_source_refuses(
    tmp_path: Path,
) -> None:
    from lifegather.memory.notes import CorrectionInput, NoteConflict, NoteService

    auth, actor, _, memory, reconcile = setup(tmp_path)
    text = "Acme Drill Qty: 1 shelf A\nAcme Drill Qty: 1 shelf B"
    source = save_text(memory, actor, SaveText(text=text, request_id="same-product"))
    fields = [
        ReceiptFields(
            name="Drill",
            manufacturer="Acme",
            model=None,
            serial=None,
            kind="mention",
            quote=quote,
            quantity=1,
            quantity_quote="Qty: 1",
        )
        for quote in text.splitlines()
    ]
    service = ReceiptService(auth.engine)
    row = service.create(
        actor,
        source.id,
        ReceiptExtraction(
            items=fields,
            explanation="Synthetic two lines need physical identity review",
        ),
    )
    before = memory.export_page(actor, "entities")
    with pytest.raises(NoteConflict, match="each other"):
        service.review(actor, automatic(row))
    assert memory.export_page(actor, "entities") == before
    assert reconcile.inventory(actor) == []
    assert service.get(actor, row["id"])["state"] == "proposed"
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=source.id,
            text="Corrected synthetic source.",
            request_id="correction",
        ),
    )
    with pytest.raises(MemoryError):
        service.review(actor, automatic(row))


def test_automatic_receipt_existing_private_http_mcp_contract() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "receipt-auto-owner")
        foreign, _ = signed_headers(app, "receipt-auto-foreign")
        engine = app.state.auth_store.engine
        service, row = draft(engine, actor, MemoryService(engine))
        request = automatic(row).model_dump()
        path = "/api/receipts/review"
        assert client.post(path, json=request).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": headers["Cookie"]}, json=request
            ).status_code
            == 403
        )
        assert client.post(path, headers=foreign, json=request).status_code == 400
        result = rpc(client, headers, "receipt_review", request).json()["result"][
            "structuredContent"
        ]
        assert result["state"] == "accepted"
        assert client.post(path, headers=headers, json=request).json() == result
        assert len(service.reconcile.inventory(actor)) == 3
        changed = {
            **request,
            "choices": [dict(choice) for choice in request["choices"]],
        }
        changed["choices"][0] = {**changed["choices"][0], "action": "skip"}
        assert client.post(path, headers=headers, json=changed).status_code == 409
