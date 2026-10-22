from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_chat import send
from test_mcp_http import rpc, signed_headers
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.chat.provider import Completion
from lifegather.chat.service import SaveText, save_text
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Entity
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError
from lifegather.reconciliation.proposals import (
    AssetExtraction,
    AssetFields,
    ProposalService,
)
from lifegather.reconciliation.receipt_models import ReceiptProposal
from lifegather.reconciliation.receipts import (
    ReceiptChoice,
    ReceiptExtraction,
    ReceiptFields,
    ReceiptPreview,
    ReceiptReview,
    ReceiptService,
)

TEXT = "Acme Drill Qty: 2\nAcme Saw Qty: 1"


def fields(name: str = "Drill", quantity: int = 2, **changes: Any) -> ReceiptFields:
    return ReceiptFields.model_validate(
        {
            "name": name,
            "manufacturer": "Acme",
            "model": None,
            "serial": None,
            "kind": "mention",
            "quote": f"Acme {name} Qty: {quantity}",
            "quantity": quantity,
            "quantity_quote": f"Qty: {quantity}",
            **changes,
        }
    )


def extraction() -> ReceiptExtraction:
    return ReceiptExtraction(
        items=[fields(), fields("Saw", 1)],
        explanation="Synthetic two-line receipt; ownership unknown.",
    )


def choices(
    service: ReceiptService, actor: Any, receipt: dict[str, Any]
) -> list[ReceiptChoice]:
    result = []
    for index, item in enumerate(receipt["items"]):
        value = ReceiptFields.model_validate({**item, "kind": "purchase"})
        preview = service.preview(
            actor, ReceiptPreview(receipt_id=receipt["id"], index=index, fields=value)
        )
        result.append(
            ReceiptChoice(
                index=index, fields=value, action="new", check=preview["check"]
            )
        )
    return result


def test_receipt_review_quantity_atomic_replay_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    source = save_text(memory, actor, SaveText(text=TEXT, request_id="source"))
    service = ReceiptService(auth.engine)
    receipt = service.create(actor, source.id, extraction())
    assert reconcile.inventory(actor) == []
    assert service.create(actor, source.id, extraction()) == receipt
    with pytest.raises(MemoryError):
        service.get(bob, receipt["id"])
    body = ReceiptReview(
        receipt_id=receipt["id"],
        request_id="accept",
        choices=choices(service, actor, receipt),
    )
    original = service.reconcile._discover_in
    calls = 0

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise MemoryError("Synthetic second-line failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.reconcile, "_discover_in", fail_second)
    with pytest.raises(MemoryError):
        service.review(actor, body)
    assert service.get(actor, receipt["id"])["state"] == "proposed"
    assert memory.list_entities(actor)["items"] == []
    monkeypatch.setattr(service.reconcile, "_discover_in", original)
    with ThreadPoolExecutor(max_workers=3) as pool:
        reviewed = list(pool.map(lambda _: service.review(actor, body), range(3)))
    assert reviewed[0] == reviewed[1] == reviewed[2]
    assert reviewed[0]["items"][0]["kind"] == "purchase"
    assert len(reconcile.inventory(actor)) == 3
    assert len(set(reviewed[0]["result"]["lines"][0]["asset_ids"])) == 2
    for asset in reconcile.inventory(actor):
        assert {
            e["source_id"] for fact in memory.facts(actor, asset) for e in fact.evidence
        } == {source.id}
    with pytest.raises(MemoryError):
        service.review(actor, body.model_copy(update={"request_id": "different"}))
    snapshot = tmp_path / "receipt-snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert ReceiptService(restored.engine).get(actor, receipt["id"]) == reviewed[0]
    restored.engine.dispose()
    auth.engine.dispose()


def test_receipt_rejects_unsupported_quantities_stale_source_and_single_overlap(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    source = save_text(memory, actor, SaveText(text=TEXT, request_id="source"))
    service = ReceiptService(auth.engine)
    invalid = [
        fields(quantity_quote=None),
        fields(quantity_quote="Qty: 1"),
        fields(quantity=1, quote="Acme Drill Qty: 2", quantity_quote=None),
        fields(name="invented"),
        fields(quantity=1, quote="Acme Saw Qty: 1", serial="UNKNOWN"),
    ]
    for item in invalid:
        with pytest.raises(MemoryError):
            service.create(
                actor,
                source.id,
                ReceiptExtraction(items=[item], explanation="Bad test"),
            )
    with pytest.raises(MemoryError):
        service.create(
            actor,
            source.id,
            ReceiptExtraction(items=[fields(), fields()], explanation="duplicate"),
        )
    receipt = service.create(actor, source.id, extraction())
    with pytest.raises(MemoryError):
        ProposalService(auth.engine).create(
            actor,
            source.id,
            AssetExtraction(
                candidate=AssetFields.model_validate(
                    fields().model_dump(exclude={"quantity", "quantity_quote"})
                ),
                explanation="single",
            ),
        )
    values = choices(service, actor, receipt)
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=source.id, text="Corrected receipt", request_id="correct"
        ),
    )
    assert service.get(actor, receipt["id"])["stale"] is True
    with pytest.raises(MemoryError):
        service.review(
            actor,
            ReceiptReview(receipt_id=receipt["id"], request_id="stale", choices=values),
        )
    rejected = service.review(
        actor, ReceiptReview(receipt_id=receipt["id"], request_id="reject", reject=True)
    )
    assert rejected["state"] == "rejected"
    assert (
        service.review(
            actor,
            ReceiptReview(receipt_id=receipt["id"], request_id="reject", reject=True),
        )
        == rejected
    )
    auth.engine.dispose()


def test_receipt_stale_duplicate_check_and_unit_links(tmp_path: Path) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    source = save_text(memory, actor, SaveText(text=TEXT, request_id="source"))
    service = ReceiptService(auth.engine)
    receipt = service.create(actor, source.id, extraction())
    reviewed = choices(service, actor, receipt)
    # A separate saved source adds matching physical items after preview.
    other = save_text(memory, actor, SaveText(text=TEXT, request_id="other"))
    draft2 = service.create(actor, other.id, extraction())
    created = service.review(
        actor,
        ReceiptReview(
            receipt_id=draft2["id"],
            request_id="other-review",
            choices=choices(service, actor, draft2),
        ),
    )
    with pytest.raises(MemoryError, match="changed"):
        service.review(
            actor,
            ReceiptReview(
                receipt_id=receipt["id"], request_id="stale-check", choices=reviewed
            ),
        )
    fresh = choices(service, actor, receipt)
    for choice in fresh:
        choice.action = "link"
        choice.asset_ids = created["result"]["lines"][choice.index]["asset_ids"]
    repeated = service.review(
        actor,
        ReceiptReview(receipt_id=receipt["id"], request_id="same-items", choices=fresh),
    )
    assert repeated["state"] == "accepted" and len(reconcile.inventory(actor)) == 3
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(Entity).where(Entity.kind == "asset")))) == 3
    auth.engine.dispose()


def test_receipt_http_mcp_consent_cache_queue_and_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = tmp_path / "key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()

    class Fake:
        calls = 0

        async def complete(self, *args: Any) -> Completion:
            self.calls += 1
            assert args[-1] is ReceiptExtraction
            return Completion(extraction().model_dump(), 20, 20)

    fake = Fake()
    app.state.chat_provider = fake
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        source = client.post(
            "/api/memories",
            headers=alice,
            json={"text": TEXT, "request_id": "receipt-source"},
        ).json()
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Synthetic",
                "secret": "synthetic-only",
            },
        ).json()["id"]
        options = {
            "source_id": source["id"],
            "credential_id": credential,
            "model": "synthetic",
        }
        assert (
            send(
                client,
                alice,
                conversation,
                "denied",
                "extract_receipt",
                TEXT,
                **options,
            ).json()["state"]
            == "failed"
        )
        assert fake.calls == 0
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        response = send(
            client, alice, conversation, "extract", "extract_receipt", TEXT, **options
        )
        assert response.json()["state"] == "complete", response.text
        identifier = response.json()["result"]["receipt_proposal_id"]
        again = send(
            client, alice, conversation, "again", "extract_receipt", TEXT, **options
        )
        assert (
            again.json()["result"]["receipt_proposal_id"] == identifier
            and fake.calls == 1
        )
        assert client.get("/api/receipts/" + identifier).status_code == 401
        assert client.get("/api/receipts/" + identifier, headers=bob).status_code == 400
        assert (
            client.get("/api/reviews?kind=receipts", headers=alice).json()["items"][0][
                "id"
            ]
            == identifier
        )
        assert (
            not rpc(client, alice, "receipt_get", {"receipt_id": identifier})
            .json()["result"]
            .get("isError")
        )
        service = ReceiptService(app.state.auth_store.engine)
        receipt = service.get(actor, identifier)
        body = ReceiptReview(
            receipt_id=identifier,
            request_id="confirm",
            choices=choices(service, actor, receipt),
        ).model_dump()
        assert (
            client.post(
                "/api/receipts/review", headers={"Cookie": alice["Cookie"]}, json=body
            ).status_code
            == 403
        )
        assert (
            client.post("/api/receipts/review", headers=bob, json=body).status_code
            == 400
        )
        accepted = client.post("/api/receipts/review", headers=alice, json=body)
        assert accepted.status_code == 200, accepted.text
        assert (
            client.post("/api/receipts/review", headers=alice, json=body).json()
            == accepted.json()
        )
        assert (
            client.get("/api/reviews?kind=receipts", headers=alice).json()["items"]
            == []
        )
        assert fake.calls == 1
        assert (
            client.get("/api/chat/sources/" + source["id"], headers=alice).json()[
                "receipt_proposal_id"
            ]
            == identifier
        )
        with Session(app.state.auth_store.engine) as db:
            assert len(list(db.scalars(select(ReceiptProposal)))) == 1


@pytest.mark.parametrize("deleted", [False, True])
def test_receipt_pdf_original_and_deleted_source(tmp_path: Path, deleted: bool) -> None:
    from test_documents import synthetic_pdf

    from lifegather.documents.service import (
        DocumentDelete,
        DocumentService,
        DocumentText,
    )

    auth, actor, _, memory, reconcile = setup(tmp_path)
    documents = DocumentService(auth.engine, files(auth.engine))
    document = documents.upload(actor, synthetic_pdf(), "synthetic.pdf")
    document = documents.save_text(
        actor,
        DocumentText(
            document_id=document["id"],
            text=TEXT,
            expected_updated_at=document["updated_at"],
        ),
    )
    service = ReceiptService(auth.engine)
    receipt = service.create(actor, document["source_id"], extraction())
    body = ReceiptReview(
        receipt_id=receipt["id"],
        request_id="confirm",
        choices=choices(service, actor, receipt),
    )
    if deleted:
        documents.delete(
            actor,
            DocumentDelete(
                document_id=document["id"], expected_updated_at=document["updated_at"]
            ),
        )
        with pytest.raises(MemoryError, match="deleted"):
            service.review(actor, body)
        assert reconcile.inventory(actor) == []
        assert (
            service.review(
                actor,
                ReceiptReview(
                    receipt_id=receipt["id"], request_id="reject", reject=True
                ),
            )["state"]
            == "rejected"
        )
    else:
        assert service.review(actor, body)["state"] == "accepted"
        assert len(reconcile.inventory(actor)) == 3
        assert documents.binary(actor, document["id"]).startswith(b"%PDF")
        assert memory.get_source(actor, document["source_id"]).text == TEXT
    auth.engine.dispose()


@pytest.mark.parametrize("deleted", [False, True])
def test_receipt_photo_provenance_and_deleted_source(
    tmp_path: Path, deleted: bool
) -> None:
    from test_photos import image_bytes

    from lifegather.photos.service import PhotoDelete, PhotoList, PhotoService

    auth, actor, _, _, reconcile = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "synthetic.jpg", "receipt", "")
    photos.save_reading(
        actor,
        photo["id"],
        {"transcription": TEXT, "candidate": None, "explanation": "Multi-item source."},
    )
    photo = photos.get(actor, photo["id"])
    service = ReceiptService(auth.engine)
    receipt = service.create(actor, photo["source_id"], extraction())
    body = ReceiptReview(
        receipt_id=receipt["id"],
        request_id="confirm",
        choices=choices(service, actor, receipt),
    )
    if deleted:
        photos.delete(
            actor,
            PhotoDelete(photo_id=photo["id"], expected_updated_at=photo["updated_at"]),
        )
        with pytest.raises(MemoryError, match="deleted"):
            service.review(actor, body)
        assert reconcile.inventory(actor) == []
        assert (
            service.review(
                actor,
                ReceiptReview(
                    receipt_id=receipt["id"], request_id="reject", reject=True
                ),
            )["state"]
            == "rejected"
        )
    else:
        assert service.review(actor, body)["state"] == "accepted"
        photo = photos.get(actor, photo["id"])
        for asset in reconcile.inventory(actor):
            assert (
                photos.list(actor, PhotoList(asset_id=asset))["items"][0]["id"]
                == photo["id"]
            )
    auth.engine.dispose()
