import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_asset_proposals import fields, review, setup
from test_chat import send
from test_mcp_http import rpc, signed_headers

from lifegather.auth.store import AuthStore
from lifegather.chat.provider import Completion, OpenAIProvider
from lifegather.chat.runner import PhotoReading
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import CorrectionInput, NoteConflict, NoteService
from lifegather.memory.service import MemoryError
from lifegather.photos.models import Photo
from lifegather.photos.service import (
    MAX_BYTES,
    PhotoDelete,
    PhotoList,
    PhotoService,
    decode,
)


def image_bytes() -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[270] = "PRIVATE metadata"
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def test_decode_strips_metadata_and_refuses_invalid_animation_and_pixel_bombs() -> None:
    decoded = decode(image_bytes())
    assert decoded.width == 200 and decoded.mime == "image/jpeg"
    with Image.open(BytesIO(decoded.preview)) as preview:
        assert not preview.getexif()
        assert b"PRIVATE" not in decoded.preview
    animation = BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        animation,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
        duration=100,
    )
    huge = BytesIO()
    Image.new("1", (5000, 5000)).save(huge, format="PNG")
    for raw in (
        b"",
        b"<svg>bad</svg>",
        b"x" * (MAX_BYTES + 1),
        image_bytes()[:100],
        animation.getvalue(),
        huge.getvalue(),
    ):
        with pytest.raises(MemoryError):
            decode(raw)


def test_upload_dedup_attachment_isolation_delete_and_restore(tmp_path: Path) -> None:
    auth, alice, bob, _, _, proposals, proposal = setup(tmp_path)
    asset = proposals.review(alice, review(proposal["id"]))["result"]["asset_ids"][0]
    photos = PhotoService(auth.engine)
    raw = image_bytes()
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(
            pool.map(
                lambda _: photos.upload(alice, raw, "receipt.jpg", "receipt", asset),
                range(3),
            )
        )
    assert len({r["id"] for r in rows}) == 1
    first = rows[0]
    assert len(photos.list(alice, PhotoList(asset_id=asset))["items"]) == 1
    assert photos.binary(alice, first["id"], True)[0] == raw
    assert photos.upload(bob, raw, "same.jpg")["id"] != first["id"]
    with pytest.raises(MemoryError):
        photos.get(bob, first["id"])
    with pytest.raises(MemoryError):
        photos.upload(bob, raw, "receipt.jpg", asset_id=asset)
    assert len(photos.list(bob, PhotoList())["items"]) == 1
    for filename in ("../x.jpg", "x\\y.jpg", "x\x00.jpg", "x" * 201):
        with pytest.raises(MemoryError):
            photos.upload(alice, raw, filename)
    backup = tmp_path / "snapshot.sqlite3"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(backup)
    restored.migrate()
    assert PhotoService(restored.engine).binary(alice, first["id"], True)[0] == raw
    with Session(auth.engine) as db:
        row = db.scalar(select(Photo).where(Photo.id == first["id"]))
        assert row is not None
        assert "original" not in row.__dict__ and "preview" not in row.__dict__
    with pytest.raises(NoteConflict):
        photos.delete(alice, PhotoDelete(photo_id=first["id"], expected_updated_at=0))
    deletion = PhotoDelete(
        photo_id=first["id"],
        expected_updated_at=photos.get(alice, first["id"])["updated_at"],
    )
    assert photos.delete(alice, deletion) == photos.delete(alice, deletion)
    with pytest.raises(MemoryError):
        photos.binary(alice, first["id"])
    assert photos.upload(alice, raw, "again.jpg")["id"] != first["id"]
    assert PhotoService(restored.engine).binary(alice, first["id"], True)[0] == raw
    restored.engine.dispose()
    auth.engine.dispose()


def reading() -> dict[str, Any]:
    return {
        "transcription": "Husqvarna 525L",
        "candidate": fields(
            name="Husqvarna 525L", kind="mention", quote="Husqvarna 525L"
        ).model_dump(),
        "explanation": "Unverified nameplate; ownership is unknown.",
    }


def test_photo_source_proposal_transaction_validation_correction_and_deletion(
    tmp_path: Path,
) -> None:
    auth, alice, _, _, _, proposals, _ = setup(tmp_path)
    photos = PhotoService(auth.engine)
    photo = photos.upload(alice, image_bytes(), "plate.jpg")
    invalid = reading()
    invalid["candidate"]["serial"] = "invented"
    with pytest.raises(MemoryError):
        photos.save_reading(alice, photo["id"], invalid)
    assert photos.get(alice, photo["id"])["source_id"] is None
    value = photos.save_reading(alice, photo["id"], reading())
    assert value == photos.save_reading(alice, photo["id"], reading())
    source = value["source_id"]
    assert photos.source_photo(alice, source)["id"] == photo["id"]  # type: ignore[index]
    corrected = NoteService(auth.engine).correct(
        alice,
        CorrectionInput(
            source_id=source, text="I own this Husqvarna 525L", request_id="correct"
        ),
    )
    assert photos.source_photo(alice, corrected["source"]["id"])["id"] == photo["id"]  # type: ignore[index]
    with pytest.raises(NoteConflict):
        proposals.review(
            alice,
            review(
                value["id"],
                fields=fields(kind="possession", quote="Husqvarna 525L").model_dump(),
            ),
        )
    latest = photos.get(alice, photo["id"])
    photos.delete(
        alice,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=latest["updated_at"]),
    )
    from lifegather.reconciliation.proposals import AssetExtraction

    with pytest.raises(MemoryError, match="deleted"):
        proposals.create(
            alice,
            corrected["source"]["id"],
            AssetExtraction(candidate=None, explanation="No item"),
        )
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count(Photo.id))) == 1
    auth.engine.dispose()


def test_upload_http_mcp_auth_headers_and_vision_consent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()

    class FakeVision:
        calls = 0

        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: type[BaseModel],
        ) -> Completion:
            self.calls += 1
            assert schema is PhotoReading
            assert payload["_image_jpeg"].startswith(b"\xff\xd8")
            assert b"PRIVATE" not in payload["_image_jpeg"]
            return Completion(reading(), 10, 10)

    fake = FakeVision()
    app.state.chat_provider = fake
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        headers = {
            **alice,
            "X-File-Name": "receipt.jpg",
            "Content-Type": "application/octet-stream",
        }
        assert (
            client.post(
                "/api/photos", content=image_bytes(), headers={"X-File-Name": "x"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/photos",
                content=image_bytes(),
                headers={**headers, "X-CSRF-Token": "bad"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/photos", content=b"x" * (MAX_BYTES + 1), headers=headers
            ).status_code
            == 413
        )
        photo = client.post(
            "/api/photos?purpose=nameplate", content=image_bytes(), headers=headers
        )
        assert photo.status_code == 201, photo.text
        identifier = photo.json()["id"]
        assert (
            client.get(f"/api/photos/{identifier}/preview", headers=bob).status_code
            == 400
        )
        original = client.get(f"/api/photos/{identifier}/original", headers=alice)
        assert original.content == image_bytes()
        assert original.headers["content-type"] == "application/octet-stream"
        assert "attachment" in original.headers["content-disposition"]
        assert original.headers["cache-control"] == "no-store"
        result = rpc(client, alice, "photo_list", {}).json()["result"]
        assert not result.get("isError"), result
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Test",
                "secret": "synthetic-key",
            },
        ).json()["id"]
        options = {
            "photo_id": identifier,
            "credential_id": credential,
            "model": "synthetic-vision",
        }
        denied = send(
            client,
            alice,
            conversation,
            "no-consent",
            "extract_photo",
            "Read photo",
            **options,
        )
        assert denied.json()["state"] == "failed" and fake.calls == 0
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        response = send(
            client,
            alice,
            conversation,
            "read",
            "extract_photo",
            "Read photo",
            **options,
        )
        assert response.json()["state"] == "complete", response.text
        proposal_id = response.json()["result"]["proposal_id"]
        again = send(
            client,
            alice,
            conversation,
            "again",
            "extract_photo",
            "Read photo",
            **options,
        )
        assert again.json()["result"]["proposal_id"] == proposal_id and fake.calls == 1
        source_id = response.json()["result"]["sources"][0]["id"]
        assert (
            client.get(f"/api/chat/sources/{source_id}", headers=alice).json()["photo"][
                "id"
            ]
            == identifier
        )
        accepted = client.post(
            "/api/chat/asset-proposals/review",
            headers=alice,
            json=review(
                proposal_id,
                fields=fields(kind="possession", quote="Husqvarna 525L").model_dump(),
            ).model_dump(),
        )
        assert accepted.status_code == 200, accepted.text
        asset = accepted.json()["result"]["asset_ids"][0]
        assert (
            len(
                client.get(f"/api/photos?asset_id={asset}", headers=alice).json()[
                    "items"
                ]
            )
            == 1
        )

        # A deleted original must discard a late provider result.
        second_image = BytesIO()
        Image.new("RGB", (3, 3), "blue").save(second_image, format="PNG")
        second = client.post(
            "/api/photos", headers=headers, content=second_image.getvalue()
        ).json()
        store = app.state.auth_store

        class DeletingProvider:
            async def complete(
                self,
                secret: str,
                model: str,
                instruction: str,
                payload: dict[str, Any],
                schema: type[BaseModel],
            ) -> Completion:
                PhotoService(store.engine).delete(
                    actor,
                    PhotoDelete(
                        photo_id=second["id"], expected_updated_at=second["updated_at"]
                    ),
                )
                return Completion(reading(), 10, 10)

        app.state.chat_provider = DeletingProvider()
        late = send(
            client,
            alice,
            conversation,
            "late",
            "extract_photo",
            "Read photo",
            **{**options, "photo_id": second["id"]},
        )
        assert late.json()["state"] == "failed"
        assert PhotoService(store.engine).get(actor, second["id"])["source_id"] is None


def test_openai_vision_wire_is_explicit_bounded_and_stateless() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert body["store"] is False and "tools" not in body
        content = body["input"][0]["content"]
        assert content[1]["type"] == "input_image"
        assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
        assert "_image_jpeg" not in content[0]["text"]
        return httpx2.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(reading())}
                        ],
                    }
                ],
            },
        )

    async def run() -> None:
        result = await OpenAIProvider(httpx2.MockTransport(handler)).complete(
            "synthetic",
            "vision-test",
            "data only",
            {"_image_jpeg": decode(image_bytes()).preview},
            PhotoReading,
        )
        assert result.value == reading()

    asyncio.run(run())


def test_detach_only_one_gallery_preserves_original_evidence_and_retry(
    tmp_path: Path,
) -> None:
    from lifegather.memory.schemas import EntityInput
    from lifegather.memory.service import MemoryService
    from lifegather.photos.service import PhotoDetach

    auth, alice, bob, _, _, proposals, proposal = setup(tmp_path)
    asset = proposals.review(alice, review(proposal["id"]))["result"]["asset_ids"][0]
    second = MemoryService(auth.engine).create_entity(
        alice,
        EntityInput(
            kind="asset",
            name="Other synthetic item",
            operation_key="other",
            source_id=proposal["source_id"],
        ),
    )
    photos = PhotoService(auth.engine)
    first = photos.upload(alice, image_bytes(), "synthetic.jpg", asset_id=asset)
    row = photos.upload(alice, image_bytes(), "synthetic.jpg", asset_id=second.id)
    body = PhotoDetach(
        photo_id=row["id"], asset_id=asset, expected_updated_at=row["updated_at"]
    )
    with pytest.raises(MemoryError):
        photos.detach(bob, body)
    with pytest.raises(NoteConflict):
        photos.detach(alice, body.model_copy(update={"expected_updated_at": 0}))
    removed = photos.detach(alice, body)
    assert photos.detach(alice, body) == removed
    assert photos.list(alice, PhotoList(asset_id=asset))["items"] == []
    assert (
        photos.list(alice, PhotoList(asset_id=second.id))["items"][0]["id"]
        == first["id"]
    )
    assert photos.binary(alice, row["id"], True)[0] == image_bytes()
    photos.upload(alice, image_bytes(), "synthetic.jpg", asset_id=asset)
    with pytest.raises(NoteConflict):
        photos.detach(alice, body)
    auth.engine.dispose()


def test_detach_http_mcp_boundaries_and_audit_preserve_evidence() -> None:
    from lifegather.memory.models import Audit
    from lifegather.memory.schemas import EntityInput, SourceInput
    from lifegather.memory.service import MemoryService

    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "detach-alice")
        bob, _ = signed_headers(app, "detach-bob")
        memory = MemoryService(app.state.auth_store.engine)
        source = memory.ingest(
            actor,
            SourceInput(
                text="Synthetic car photo",
                source_type="conversation",
                namespace="synthetic",
                external_id="car",
            ),
        )
        asset = memory.create_entity(
            actor,
            EntityInput(
                name="Synthetic car",
                kind="asset",
                source_id=source.id,
                operation_key="car",
            ),
        )
        photos = PhotoService(memory.engine)
        row = photos.upload(actor, image_bytes(), "car.jpg", asset_id=asset.id)
        body = {
            "photo_id": row["id"],
            "asset_id": asset.id,
            "expected_updated_at": row["updated_at"],
        }
        assert client.post("/api/photos/detach", json=body).status_code == 401
        assert (
            client.post(
                "/api/photos/detach", headers={"Cookie": alice["Cookie"]}, json=body
            ).status_code
            == 403
        )
        assert (
            client.post("/api/photos/detach", headers=bob, json=body).status_code == 400
        )
        assert rpc(client, bob, "photo_detach", body).json()["result"]["isError"]
        assert (
            client.post("/api/photos/detach", headers=alice, json=body).status_code
            == 200
        )
        assert (
            not rpc(client, alice, "photo_detach", body).json()["result"].get("isError")
        )
        assert photos.binary(actor, row["id"], True)[0] == image_bytes()
        assert memory.get_source(actor, source.id).text == "Synthetic car photo"
        with Session(memory.engine) as db:
            audit = list(
                db.scalars(select(Audit).where(Audit.operation == "photo_detached"))
            )
            assert len(audit) == 1 and audit[0].target_id == f"{row['id']}:{asset.id}"


def test_detach_rejects_oversized_request_before_parsing() -> None:
    with TestClient(create_app()) as client:
        assert (
            client.post("/api/photos/detach", content=b" " * 32769).status_code == 413
        )
