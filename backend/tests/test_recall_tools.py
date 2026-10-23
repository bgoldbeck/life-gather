import json

import pytest
from fastapi.testclient import TestClient

from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService
from lifegather.main import create_app
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryService
from lifegather.profiles.service import ProfileChange, ProfileCreate, ProfileService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_recall_preserves_sources_private_ownership_and_distinct_items() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "alice@example.test", "Alice", now=2000000000).user
        bob = store.login("bob", "bob@example.test", "Bob", now=2000000000).user
        profiles = ProfileService(store.engine)
        car = profiles.create(
            alice,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="Synthetic test vehicle",
                operation_key="car",
            ),
        )
        other = profiles.create(
            alice,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="A distinct synthetic test vehicle",
                operation_key="car-two",
            ),
        )
        profiles.create(
            bob,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="FOREIGN PRIVATE STATEMENT",
                operation_key="car",
            ),
        )
        original = profiles.save(
            alice,
            ProfileChange(
                entity_id=car.id,
                field="model",
                value="Model A",
                text="Model A",
                operation_key="model",
            ),
        )
        profiles.save(
            alice,
            ProfileChange(
                entity_id=car.id,
                field="model",
                value="Model B",
                text="Model B",
                replaces_id=original.id,
                operation_key="correct-model",
            ),
        )
        memory = MemoryService(store.engine)
        source = memory.ingest(
            alice, SourceInput(text="Synthetic car is stored at Synthetic garage")
        )
        garage = memory.create_entity(
            alice,
            EntityInput(
                name="Synthetic garage",
                kind="place",
                source_id=source.id,
                operation_key="garage",
            ),
        )
        memory.assert_fact(
            alice,
            FactInput(
                subject_id=car.id,
                predicate="stored_in",
                object_id=garage.id,
                source_id=source.id,
                status="inferred",
                operation_key="location",
            ),
        )
        context = RecallTools(ChatService(store.engine)).collect(
            alice,
            RecallPlan(
                query="Synthetic",
                entity_names=["Synthetic car"],
                include_connections=True,
            ),
        )
        assert {record["entity"]["id"] for record in context["records"]} == {
            car.id,
            other.id,
        }
        assert all(record["ambiguous_name"] for record in context["records"])
        encoded = json.dumps(context, ensure_ascii=False)
        assert "Model B" in encoded
        assert "FOREIGN PRIVATE" not in encoded
        assert original.id not in {
            fact["id"] for record in context["records"] for fact in record["facts"]
        }
        assert "stored_in" in encoded and "inferred" in encoded
        assert len(context["evidence"]) <= 8
        assert len(encoded.encode()) <= 24000
        limited = RecallTools(ChatService(store.engine)).collect(
            alice,
            RecallPlan(
                query="Synthetic",
                entity_names=["Synthetic car"],
                include_connections=True,
            ),
            max_bytes=3000,
        )
        assert len(json.dumps(limited, ensure_ascii=False).encode()) <= 3000
        assert limited["truncated"] is True
        for record in limited["records"]:
            for fact in record["facts"]:
                if fact["predicate"] == "profile_model":
                    assert fact["value"] == "Model B"


def test_answer_uses_owned_profile_read_results_and_real_source_ids() -> None:
    from typing import Any

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from pydantic import BaseModel

    from lifegather.chat.provider import Completion

    class SourcedProvider:
        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: type[BaseModel],
        ) -> Completion:
            if schema is RecallPlan:
                return Completion(
                    {
                        "query": "Synthetic",
                        "entity_names": ["Synthetic car"],
                        "include_connections": False,
                    },
                    5,
                    5,
                )
            fact = next(
                fact
                for record in payload["records"]
                for fact in record["facts"]
                if fact["predicate"] == "profile_model"
            )
            assert fact["value"] == "Model B" and fact["status"] == "stated"
            return Completion(
                {
                    "text": "Your sourced profile states Model B.",
                    "source_ids": [fact["evidence"][0]["source_id"]],
                },
                5,
                5,
            )

    app = create_app()
    with TestClient(app) as client:
        store = app.state.auth_store
        signed = store.login("recall", "recall@example.test", "Recall", now=2000000000)
        client.cookies.set("lifegather_session", signed.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        service = ProfileService(store.engine)
        car = service.create(
            signed.user,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="A synthetic vehicle",
                operation_key="car",
            ),
        )
        fact = service.save(
            signed.user,
            ProfileChange(
                entity_id=car.id,
                field="model",
                value="Model B",
                text="Model B",
                operation_key="model",
            ),
        )
        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(signed.user, "ai", "openai", "Synthetic", "synthetic")
        vault.set_preferences(signed.user, True)
        app.state.chat_provider = SourcedProvider()
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        turn = client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=headers,
            json={
                "mode": "ask",
                "request_id": "recall",
                "text": "What is my Synthetic car model?",
                "model": "synthetic",
                "credential_id": credential.id,
            },
        ).json()
        assert turn["state"] == "complete"
        assert turn["result"]["records"][0]["id"] == car.id
        assert turn["result"]["sources"][0]["id"] == fact.evidence[0]["source_id"]
