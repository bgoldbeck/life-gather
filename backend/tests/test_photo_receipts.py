from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from database_support import restore_copy
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session
from stored_files import files
from test_chat import send
from test_mcp_http import rpc, signed_headers
from test_photos import image_bytes, reading
from test_receipts import TEXT, choices, extraction
from test_reconciliation import setup

from lifegather.auth.store import AuthStore
from lifegather.chat.provider import Completion
from lifegather.chat.service import ChatService
from lifegather.credentials.keygen import generate
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.history import FieldHistory, FieldHistoryRead, event_origin
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError
from lifegather.photos.service import PhotoDelete, PhotoList, PhotoService
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService


def receipt_reading() -> dict[str, Any]:
    return {"transcription": TEXT, **extraction().model_dump()}


class SyntheticVision:
    def __init__(self) -> None:
        self.value = receipt_reading()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.before_return: Callable[[], None] | None = None

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion:
        self.calls.append((schema.__name__, payload))
        assert "untrusted" in instruction.lower()
        if self.before_return:
            self.before_return()
        return Completion(deepcopy(self.value), 10, 10)


@pytest.fixture
def photo_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Any, ...]]:
    from lifegather.main import create_app

    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    provider = SyntheticVision()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "receipt-photo-owner")
        foreign, _ = signed_headers(app, "receipt-photo-foreign")
        chat = ChatService(app.state.auth_store.engine)
        photo = PhotoService(chat.engine, files(chat.engine)).upload(
            actor, image_bytes(), "receipt.jpg", "receipt"
        )
        connection = app.state.private_settings.save(
            actor, "ai", "openai", "Synthetic", "synthetic-only"
        )
        app.state.private_settings.set_preferences(actor, True)
        options = {
            "photo_id": photo["id"],
            "credential_id": connection.id,
            "model": "synthetic",
        }
        yield client, headers, foreign, actor, chat, photo, provider, options


def test_photo_receipt_chat_replay_review_private_source_and_snapshot(
    photo_chat: tuple[Any, ...], tmp_path: Path
) -> None:
    client, headers, foreign, actor, chat, photo, provider, options = photo_chat
    conversation = chat.create(actor)["id"]
    response = send(
        client,
        headers,
        conversation,
        "receipt",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    )
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "complete", result
    assert provider.calls[0][0] == "PhotoReceiptReading"
    assert set(provider.calls[0][1]) == {"_image_jpeg", "task"}
    assert provider.calls[0][1]["_image_jpeg"].startswith(b"\xff\xd8")
    receipt_id = result["result"]["receipt_proposal_id"]
    source_id = result["result"]["sources"][0]["id"]
    with Session(chat.engine) as db:
        origin = event_origin(db, actor, source_id, ("source_ingested",))
        assert origin is not None
        assert origin["method"] == "ai_extraction" and origin["provider"] == "openai"
        assert origin["model"] == "synthetic" and origin["related_id"] == conversation
    assert chat.usage(actor)["requests"] == 1
    assert chat.memory.export_page(actor, "entities")["items"] == []
    service = ReceiptService(chat.engine)
    draft = service.get(actor, receipt_id)
    assert [row["quantity"] for row in draft["items"]] == [2, 1]
    assert all(row["kind"] == "mention" for row in draft["items"])
    assert (
        PhotoService(chat.engine, files(chat.engine)).get(actor, photo["id"])[
            "source_id"
        ]
        == source_id
    )
    assert (
        client.get(f"/api/chat/sources/{source_id}", headers=headers).json()["photo"][
            "id"
        ]
        == photo["id"]
    )
    assert rpc(client, foreign, "receipt_get", {"receipt_id": receipt_id}).json()[
        "result"
    ]["isError"]
    for request_id, mode in [
        ("receipt", "extract_photo_receipt"),
        ("again", "extract_photo_receipt"),
        ("single", "extract_photo"),
    ]:
        replay = send(
            client,
            headers,
            conversation,
            request_id,
            mode,
            "Read receipt lines for review.",
            **options,
        ).json()
        assert replay["result"]["receipt_proposal_id"] == receipt_id
    assert len(provider.calls) == 1 and chat.usage(actor)["requests"] == 1
    reviewed = service.review(
        actor,
        ReceiptReview(
            receipt_id=receipt_id,
            request_id="review",
            choices=choices(service, actor, draft),
        ),
    )
    identifiers = [
        identifier
        for row in reviewed["result"]["lines"]
        for identifier in row["asset_ids"]
    ]
    assert len(identifiers) == len(set(identifiers)) == 3
    history = FieldHistory(chat.engine).get(
        actor, FieldHistoryRead(entity_id=identifiers[0], field="owned")
    )
    assert history["items"][0]["origin"]["method"] == "review"
    assert history["items"][0]["proposal_origin"]["provider"] == "openai"
    for identifier in identifiers:
        assert (
            PhotoService(chat.engine, files(chat.engine)).list(
                actor, PhotoList(asset_id=identifier)
            )["items"][0]["id"]
            == photo["id"]
        )
    snapshot = tmp_path / "restore.jsonl"
    operator_snapshot(chat.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    assert ReceiptService(restored.engine).get(actor, receipt_id) == reviewed
    restored.engine.dispose()


@pytest.mark.parametrize(
    "invalid",
    ["quote", "ownership", "quantity", "units", "lines", "transcription", "money"],
)
def test_invalid_photo_receipt_rolls_back_transcription_and_draft(
    tmp_path: Path, invalid: str
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")
    value = receipt_reading()
    if invalid == "quote":
        value["items"][1]["quote"] = "invented quote"
    elif invalid == "ownership":
        value["items"][1]["kind"] = "purchase"
    elif invalid == "quantity":
        value["items"][1]["quantity"] = 2
    elif invalid == "units":
        value["items"][0]["quantity"] = 20
    elif invalid == "lines":
        value["items"] *= 5
    elif invalid == "money":
        value["items"][0]["price"] = "49.90"
    else:
        value["transcription"] = "x" * 4001
    before = memory.export_page(actor, "sources")
    with pytest.raises(ValueError):
        photos.save_receipt_reading(actor, photo["id"], value)
    assert photos.get(actor, photo["id"])["source_id"] is None
    assert memory.export_page(actor, "sources") == before
    assert memory.export_page(actor, "entities")["items"] == []


def test_photo_receipt_refuses_foreign_deleted_or_changed_transcription(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, _, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")
    with pytest.raises(MemoryError):
        photos.save_receipt_reading(foreign, photo["id"], receipt_reading())
    saved = photos.save_receipt_reading(actor, photo["id"], receipt_reading())
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=saved["source_id"],
            text="Corrected synthetic receipt.",
            request_id="correct",
        ),
    )
    with pytest.raises(MemoryError):
        photos.save_receipt_reading(actor, photo["id"], receipt_reading())
    current = photos.get(actor, photo["id"])
    photos.delete(
        actor,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=current["updated_at"]),
    )
    with pytest.raises(MemoryError):
        photos.save_receipt_reading(actor, photo["id"], receipt_reading())


def test_receipt_photo_uses_current_transcription_after_inactive_single_review(
    photo_chat: tuple[Any, ...],
) -> None:
    client, headers, _, actor, chat, photo, provider, options = photo_chat
    PhotoService(chat.engine, files(chat.engine)).save_reading(
        actor,
        photo["id"],
        {
            "transcription": TEXT,
            "candidate": None,
            "explanation": "Multiple items; review separately.",
        },
    )
    source_id = PhotoService(chat.engine, files(chat.engine)).get(actor, photo["id"])[
        "source_id"
    ]
    corrected = NoteService(chat.engine).correct(
        actor,
        CorrectionInput(
            source_id=source_id,
            text=TEXT + "\nSynthetic corrected transcription.",
            request_id="correct",
        ),
    )
    provider.value = extraction().model_dump()
    conversation = chat.create(actor)["id"]
    result = send(
        client,
        headers,
        conversation,
        "receipt",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    ).json()
    assert result["state"] == "complete", result
    assert provider.calls[0] == (
        "ReceiptExtraction",
        {"saved_note": corrected["source"]["text"]},
    )
    assert result["result"]["sources"][0]["id"] == corrected["source"]["id"]


def test_active_single_photo_proposal_blocks_receipt_before_provider(
    photo_chat: tuple[Any, ...],
) -> None:
    client, headers, _, actor, chat, photo, provider, options = photo_chat
    PhotoService(chat.engine, files(chat.engine)).save_reading(
        actor, photo["id"], reading()
    )
    conversation = chat.create(actor)["id"]
    result = send(
        client,
        headers,
        conversation,
        "receipt",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    ).json()
    assert result["state"] == "failed"
    assert provider.calls == [] and chat.usage(actor)["requests"] == 0


@pytest.mark.parametrize("empty_text", ["", "Synthetic unreadable receipt."])
def test_unclear_receipt_keeps_evidence_without_inventory(
    tmp_path: Path, empty_text: str
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "unclear.jpg")
    result = photos.save_receipt_reading(
        actor,
        photo["id"],
        {"transcription": empty_text, "items": [], "explanation": "No legible item."},
    )
    assert result["state"] == "no_items" and result["items"] == []
    source_photo = photos.source_photo(actor, result["source_id"])
    assert source_photo is not None and source_photo["id"] == photo["id"]
    assert memory.export_page(actor, "entities")["items"] == []
    assert photos.save_receipt_reading(actor, photo["id"], receipt_reading()) == result


def test_concurrent_photo_receipt_saves_keep_one_original_and_review(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")

    def save(_: int) -> dict[str, Any]:
        return photos.save_receipt_reading(actor, photo["id"], receipt_reading())

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(save, range(2)))
    assert first == second
    assert len(memory.export_page(actor, "sources")["items"]) == 1
    assert memory.export_page(actor, "entities")["items"] == []


@pytest.mark.parametrize("race", ["deleted", "cancelled"])
def test_photo_receipt_discards_provider_result_after_delete_or_cancel(
    photo_chat: tuple[Any, ...], race: str
) -> None:
    client, headers, _, actor, chat, photo, provider, options = photo_chat

    def change() -> None:
        if race == "deleted":
            photos = PhotoService(chat.engine, files(chat.engine))
            current = photos.get(actor, photo["id"])
            photos.delete(
                actor,
                PhotoDelete(
                    photo_id=photo["id"], expected_updated_at=current["updated_at"]
                ),
            )
        else:
            chat.cancel(actor, "race")

    provider.before_return = change
    conversation = chat.create(actor)["id"]
    result = send(
        client,
        headers,
        conversation,
        "race",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    ).json()
    assert result["state"] in {"failed", "canceled"}
    assert (
        PhotoService(chat.engine, files(chat.engine)).get(actor, photo["id"])[
            "source_id"
        ]
        is None
    )
    assert chat.memory.export_page(actor, "sources")["items"] == []
    assert chat.memory.export_page(actor, "entities")["items"] == []


def test_photo_receipt_without_permission_or_with_foreign_original_makes_no_call(
    photo_chat: tuple[Any, ...],
) -> None:
    client, headers, foreign, actor, chat, _, provider, options = photo_chat
    foreign_conversation = client.post(
        "/api/chat/conversations", headers=foreign
    ).json()["id"]
    result = send(
        client,
        foreign,
        foreign_conversation,
        "foreign",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    ).json()
    assert result["state"] == "failed" and provider.calls == []
    # Disable permission through the actual authenticated settings endpoint.
    assert (
        client.put(
            "/api/settings", headers=headers, json={"allow_external_ai": False}
        ).status_code
        == 204
    )
    result = send(
        client,
        headers,
        chat.create(actor)["id"],
        "denied",
        "extract_photo_receipt",
        "Read receipt lines for review.",
        **options,
    ).json()
    assert result["state"] == "failed" and provider.calls == []
    assert chat.usage(actor)["requests"] == 0


@pytest.mark.parametrize(
    "text",
    ["Acme Drill Qty: 2\nAcme Saw Qty: 1", "Acme Drill Qty: 1\nAcme Drill Qty: 2"],
)
def test_photo_receipt_cannot_hide_multiple_units_by_shortening_the_quote(
    tmp_path: Path, text: str
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")
    value = receipt_reading()
    value["transcription"] = text
    value["items"] = [
        {
            **value["items"][0],
            "quote": "Acme Drill",
            "quantity": 1,
            "quantity_quote": None,
        }
    ]
    with pytest.raises(MemoryError, match="quantity"):
        photos.save_receipt_reading(actor, photo["id"], value)
    assert photos.get(actor, photo["id"])["source_id"] is None
    assert memory.export_page(actor, "sources")["items"] == []


@pytest.mark.parametrize(
    "text", ["Acme Drill USD 49.90 model 2x4", "Acme Drill\nAcme Saw Qty: 2"]
)
def test_single_item_ignores_prices_dimensions_and_other_line_quantities(
    tmp_path: Path, text: str
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")
    value = receipt_reading()
    value["transcription"] = text
    value["items"] = [
        {
            **value["items"][0],
            "quote": "Acme Drill",
            "quantity": 1,
            "quantity_quote": None,
        }
    ]
    result = photos.save_receipt_reading(actor, photo["id"], value)
    assert result["state"] == "proposed" and result["items"][0]["quantity"] == 1


def test_photo_receipt_accepts_all_eight_lines_and_twenty_reviewed_units(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, reconcile = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "receipt.jpg")
    value = receipt_reading()
    value["items"] = [
        {
            **value["items"][0],
            "name": f"Tool {i}",
            "quote": f"Acme Tool {i} Qty: {quantity}",
            "quantity": quantity,
            "quantity_quote": f"Qty: {quantity}",
        }
        for i, quantity in enumerate([2, 2, 2, 2, 2, 2, 2, 6])
    ]
    value["transcription"] = "\n".join(item["quote"] for item in value["items"])
    service = ReceiptService(auth.engine)
    draft = photos.save_receipt_reading(actor, photo["id"], value)
    assert len(draft["items"]) == 8 and reconcile.inventory(actor) == []
    accepted = service.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="review",
            choices=choices(service, actor, draft),
        ),
    )
    assert (
        len(accepted["result"]["lines"]) == 8 and len(reconcile.inventory(actor)) == 20
    )
