from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from test_chat import send
from test_mcp_http import signed_headers
from test_photos import image_bytes, reading

from lifegather.chat.provider import Completion
from lifegather.chat.runner import PhotoReading
from lifegather.chat.service import ChatService
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.reconciliation.service import ReconciliationService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_saved_photo_read_stays_in_selected_conversation_and_reuses_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()

    class SyntheticVision:
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
            assert set(payload) == {"_image_jpeg", "task"}
            return Completion(reading(), 10, 10)

    provider = SyntheticVision()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "chat-photo-owner")
        foreign, _ = signed_headers(app, "chat-photo-foreign")
        chat = ChatService(app.state.auth_store.engine)
        selected = chat.create(actor)["id"]
        other = chat.create(actor)["id"]
        saved = send(
            client,
            headers,
            selected,
            "note",
            "save",
            "Synthetic preexisting conversation memory.",
        ).json()
        upload_headers = {
            **headers,
            "Content-Type": "application/octet-stream",
            "X-File-Name": "synthetic.jpg",
        }
        uploaded = client.post(
            "/api/photos?purpose=nameplate",
            headers=upload_headers,
            content=image_bytes(),
        )
        assert uploaded.status_code == 201 and provider.calls == 0
        photo = uploaded.json()
        credential = app.state.private_settings.save(
            actor, "ai", "openai", "Synthetic", "synthetic-only"
        )
        app.state.private_settings.set_preferences(actor, True)
        options = {
            "photo_id": photo["id"],
            "credential_id": credential.id,
            "model": "synthetic-vision",
        }
        result = send(
            client,
            headers,
            selected,
            "photo",
            "extract_photo",
            "Read this photo for a reviewed asset proposal.",
            **options,
        ).json()
        assert result["state"] == "complete" and provider.calls == 1
        replay = send(
            client,
            headers,
            selected,
            "photo",
            "extract_photo",
            "Read this photo for a reviewed asset proposal.",
            **options,
        ).json()
        assert replay == result
        reused = send(
            client,
            headers,
            selected,
            "photo-again",
            "extract_photo",
            "Read this photo for a reviewed asset proposal.",
            **options,
        ).json()
        assert reused["result"]["proposal_id"] == result["result"]["proposal_id"]
        assert provider.calls == 1 and chat.usage(actor)["requests"] == 1
        turns = client.get(
            f"/api/chat/conversations/{selected}/turns", headers=headers
        ).json()["items"]
        assert [row["id"] for row in turns] == [saved["id"], result["id"], reused["id"]]
        assert (
            client.get(
                f"/api/chat/conversations/{other}/turns", headers=headers
            ).json()["items"]
            == []
        )
        source = result["result"]["sources"][0]["id"]
        assert (
            client.get(f"/api/chat/sources/{source}", headers=headers).json()["photo"][
                "id"
            ]
            == photo["id"]
        )
        assert (
            client.get(f"/api/chat/sources/{source}", headers=foreign).status_code
            == 400
        )
        assert ReconciliationService(chat.engine).inventory(actor) == []


def test_chat_upload_is_private_deduplicated_and_needs_no_ai_permission() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "upload-owner")
        foreign, foreign_actor = signed_headers(app, "upload-foreign")
        upload_headers = {
            **headers,
            "Content-Type": "application/octet-stream",
            "X-File-Name": "Synthetic%20label.jpg",
        }
        raw = image_bytes()
        denied = {
            k: v for k, v in upload_headers.items() if k.lower() != "x-csrf-token"
        }
        assert (
            client.post("/api/photos", headers=denied, content=raw).status_code == 403
        )
        result = client.post(
            "/api/photos?purpose=nameplate", headers=upload_headers, content=raw
        )
        assert result.status_code == 201
        photo = result.json()
        replay = client.post(
            "/api/photos?purpose=nameplate", headers=upload_headers, content=raw
        )
        assert replay.status_code == 201 and replay.json() == photo
        assert photo["filename"] == "Synthetic label.jpg"
        assert photo["purpose"] == "nameplate" and photo["source_id"] is None
        listed = client.get("/api/photos", headers=headers).json()["items"]
        assert [row["id"] for row in listed] == [photo["id"]]
        assert client.get("/api/photos", headers=foreign).json()["items"] == []
        assert (
            client.get(
                f"/api/photos/{photo['id']}/original", headers=foreign
            ).status_code
            == 400
        )
        second = client.post(
            "/api/photos", headers={**foreign, "X-File-Name": "other.jpg"}, content=raw
        )
        assert second.status_code == 201 and second.json()["id"] != photo["id"]
        chat = ChatService(app.state.auth_store.engine)
        assert (
            chat.usage(actor)["requests"] == chat.usage(foreign_actor)["requests"] == 0
        )
        assert (
            client.get("/api/chat/conversations", headers=headers).json()["items"] == []
        )
        assert ReconciliationService(chat.engine).inventory(actor) == []
