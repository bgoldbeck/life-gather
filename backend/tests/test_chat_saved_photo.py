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
from lifegather.photos.service import PhotoService
from lifegather.reconciliation.service import ReconciliationService


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
        photo = PhotoService(chat.engine).upload(actor, image_bytes(), "synthetic.jpg")
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
