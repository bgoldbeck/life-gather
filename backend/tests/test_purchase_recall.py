import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from stored_files import files
from test_purchase_details import SOURCE, accepted, body
from test_receipts import choices, extraction
from test_reconciliation import setup

from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService
from lifegather.main import create_app
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService

pytestmark = pytest.mark.usefixtures("configured_database")

PLAN = RecallPlan(
    query="unmatchableword", entity_names=["Drill"], include_connections=False
)


def purchases(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for record in context["records"] for p in record["purchases"]]


def test_recall_latest_purchase_claims_unknowns_withdrawal_and_budget(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    receipt = accepted(auth.engine, actor)
    details = PurchaseDetails(auth.engine)
    tools = RecallTools(ChatService(auth.engine))
    assert all(
        p["detail_status"] == "not_recorded"
        for p in purchases(tools.collect(actor, PLAN))
    )
    claim = details.save(actor, body(receipt))
    context = tools.collect(actor, PLAN)
    lines = purchases(context)
    assert len(lines) == 2 and len({p["receipt_line_key"] for p in lines}) == 1
    assert all(p["claim"]["total_minor"] == 4990 and p["quantity"] == 2 for p in lines)
    assert all(
        p["claim"]["purchase_date"] == "2026-10-18" and p["source_current"]
        for p in lines
    )
    assert {p["source_id"] for p in lines} <= {e["id"] for e in context["evidence"]}
    assert not purchases(tools.collect(bob, PLAN))
    keyword_only = tools.collect(
        actor, RecallPlan(query="Acme", entity_names=[], include_connections=False)
    )
    assert not keyword_only["records"]
    assert any(
        e.get("receipt_review_id") == receipt["id"] for e in keyword_only["evidence"]
    )
    for budget in (1200, 2400, 5000):
        bounded = tools.collect(actor, PLAN, max_bytes=budget)
        assert len(json.dumps(bounded, ensure_ascii=False).encode()) <= budget
        for p in purchases(bounded):
            assert p["claim"]["line_total"] == "49.90"
    details.save(
        actor,
        body(
            receipt,
            request_id="withdraw",
            expected_head=claim["id"],
            line_total=None,
            money_quote=None,
            purchase_date=None,
            date_quote=None,
            reason="Withdraw unsupported details",
        ),
    )
    context = tools.collect(actor, PLAN)
    assert all(
        p["detail_status"] == "withdrawn" and p["claim"]["line_total"] is None
        for p in purchases(context)
    )
    assert (
        "49.90" in context["evidence"][0]["text"]
    )  # Raw history must not restore a withdrawn claim.
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=receipt["source_id"],
            text="Corrected receipt",
            request_id="correct",
        ),
    )
    context = tools.collect(actor, PLAN)
    assert all(not p["source_current"] for p in purchases(context))
    assert any(e["has_later_note_correction"] for e in context["evidence"])
    auth.engine.dispose()


@pytest.mark.parametrize("currency,amount", [("JPY", "1234"), ("EUR", "12.34")])
def test_recall_keeps_currency_precision_and_current_associations(
    tmp_path: Path, currency: str, amount: str
) -> None:
    auth, actor, _, _, reconcile = setup(tmp_path)
    source = SOURCE.replace("USD 49.90", f"{currency} {amount}")
    receipt = accepted(auth.engine, actor, source)
    PurchaseDetails(auth.engine).save(
        actor,
        body(
            receipt,
            currency=currency,
            line_total=amount,
            money_quote=source.split("\n")[0],
        ),
    )
    tools = RecallTools(ChatService(auth.engine))
    assert all(
        p["claim"]["currency"] == currency and p["claim"]["line_total"] == amount
        for p in purchases(tools.collect(actor, PLAN))
    )
    line = receipt["result"]["lines"][0]
    decision = reconcile.dismiss(actor, line["id"], line["decision_id"])
    assert not purchases(tools.collect(actor, PLAN))
    reconcile.undo(actor, decision.decision_id)
    assert len(purchases(tools.collect(actor, PLAN))) == 2
    auth.engine.dispose()


@pytest.mark.parametrize("kind", ["photo", "pdf"])
def test_named_record_recall_preserves_deleted_file_provenance(
    tmp_path: Path, kind: str
) -> None:
    from test_documents import synthetic_pdf
    from test_photos import image_bytes

    from lifegather.documents.service import (
        DocumentDelete,
        DocumentService,
        DocumentText,
    )
    from lifegather.photos.service import PhotoDelete, PhotoService

    auth, actor, _, _, _ = setup(tmp_path)
    if kind == "pdf":
        docs = DocumentService(auth.engine, files(auth.engine))
        original = docs.upload(actor, synthetic_pdf(), "synthetic.pdf")
        original = docs.save_text(
            actor,
            DocumentText(
                document_id=original["id"],
                text=SOURCE,
                expected_updated_at=original["updated_at"],
            ),
        )
    else:
        photos = PhotoService(auth.engine, files(auth.engine))
        original = photos.upload(actor, image_bytes(), "synthetic.jpg", "receipt", "")
        photos.save_reading(
            actor,
            original["id"],
            {
                "transcription": SOURCE,
                "candidate": None,
                "explanation": "Synthetic multi-item receipt",
            },
        )
        original = photos.get(actor, original["id"])
    service = ReceiptService(auth.engine)
    draft = service.create(actor, original["source_id"], extraction())
    receipt = service.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="confirm",
            choices=choices(service, actor, draft),
        ),
    )
    PurchaseDetails(auth.engine).save(actor, body(receipt))
    if kind == "pdf":
        docs.delete(
            actor,
            DocumentDelete(
                document_id=original["id"], expected_updated_at=original["updated_at"]
            ),
        )
    else:
        original = photos.get(actor, original["id"])
        photos.delete(
            actor,
            PhotoDelete(
                photo_id=original["id"], expected_updated_at=original["updated_at"]
            ),
        )
    context = RecallTools(ChatService(auth.engine)).collect(actor, PLAN)
    entry = next(e for e in context["evidence"] if e["id"] == receipt["source_id"])
    assert entry["document" if kind == "pdf" else "photo"]["deleted"] is True
    assert ("PDF" if kind == "pdf" else "photo") in entry["status"]
    assert all(not p["source_current"] for p in purchases(context))
    auth.engine.dispose()


def test_chat_sends_latest_typed_claims_with_citations_using_existing_two_calls() -> (
    None
):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from test_mcp_http import signed_headers

    from lifegather.chat.provider import Completion

    app = create_app()

    class Fake:
        calls = 0

        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: Any,
        ) -> Completion:
            self.calls += 1
            if schema is RecallPlan:
                return Completion(PLAN.model_dump(), 5, 5)
            entries = purchases(payload)
            assert entries and all(p["claim"]["line_total"] == "49.90" for p in entries)
            assert (
                "never infer a per-unit price" in instruction
                and "Withdrawn" in instruction
            )
            assert "sum repeated" in instruction and "receipt_line_key" in instruction
            assert (
                "absent or omitted" in instruction
                and "do not substitute" in instruction
            )
            return Completion(
                {
                    "text": "The receipt line totals USD 49.90 for two units; "
                    "individual unit prices are unknown.",
                    "source_ids": [entries[0]["source_id"]],
                },
                5,
                5,
            )

    with TestClient(app) as client:
        headers, actor = signed_headers(app, "alice")
        receipt = accepted(app.state.auth_store.engine, actor)
        PurchaseDetails(app.state.auth_store.engine).save(actor, body(receipt))
        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(actor, "ai", "openai", "Synthetic", "synthetic")
        vault.set_preferences(actor, True)
        fake = Fake()
        app.state.chat_provider = fake
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        response = client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=headers,
            json={
                "mode": "ask",
                "request_id": "question",
                "text": "What did my Drill receipt line cost?",
                "model": "synthetic",
                "credential_id": credential.id,
            },
        )
        turn = response.json()
        assert turn["state"] == "complete", turn
        assert (
            fake.calls == 2
            and turn["result"]["sources"][0]["id"] == receipt["source_id"]
        )
        assert any(t["tool"] == "asset_purchases" for t in turn["result"]["read_trace"])
