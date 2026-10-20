import json
from pathlib import Path
from typing import Any

import pytest
from test_maintenance import change, plan, prepared

from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryService


def test_source_http_mcp_and_fake_provider_share_current_typed_evidence() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    from test_mcp_http import rpc, signed_headers

    from lifegather.chat.provider import Completion
    from lifegather.main import create_app
    from lifegather.profiles.service import ProfileCreate, ProfileService

    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "task-recall-alice")
        bob, _ = signed_headers(app, "task-recall-bob")
        vehicle = ProfileService(app.state.auth_store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="Synthetic vehicle",
                operation_key="car",
            ),
        )
        tasks = MaintenanceService(app.state.auth_store.engine)
        created = tasks.create(
            actor,
            plan(
                vehicle.id,
                state="completed",
                completed_on="2026-10-19",
                text="Obsoletemarker completed.",
            ),
        )
        task = tasks.get(actor, created["id"])
        old_source = task["revision"]["source_id"]
        tasks.revise(
            actor,
            change(
                task,
                "reopen",
                state="open",
                due_on=None,
                completed_on=None,
                text="Completion entered in error; reopened.",
            ),
        )
        current = tasks.get(actor, created["id"])
        current_source = current["revision"]["source_id"]
        path = f"/api/chat/sources/{old_source}"
        original = client.get(path, headers=alice)
        assert (
            original.status_code == 200
            and original.headers["cache-control"] == "no-store"
        )
        metadata = original.json()["maintenance_context"]
        assert metadata["is_current_revision"] is False
        assert metadata["current_source_id"] == current_source
        assert "Obsoletemarker completed." in original.json()["text"]
        assert client.get(path, headers=bob).status_code == 400
        result = rpc(client, alice, "memory_source", {"source_id": old_source}).json()[
            "result"
        ]
        assert not result.get("isError")
        mcp = result["structuredContent"]["maintenance_context"]
        assert {k: v for k, v in mcp.items() if k != "read_at"} == {
            k: v for k, v in metadata.items() if k != "read_at"
        }
        denied = rpc(client, bob, "memory_source", {"source_id": old_source}).json()[
            "result"
        ]
        assert denied["isError"] and "Synthetic car" not in json.dumps(denied)

        class SourcedProvider:
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
                if schema is RecallPlan:
                    return Completion(
                        {
                            "query": "Obsoletemarker",
                            "entity_names": [],
                            "include_connections": False,
                        },
                        1,
                        1,
                    )
                assert "old raw completion text" in instruction
                evidence = {row["id"]: row for row in payload["evidence"]}
                head = evidence[current_source]["maintenance_context"]
                assert head["is_current_revision"] and head["state"] == "open"
                assert head["due_on"] is None and head["completed_on"] is None
                assert (
                    evidence[old_source]["maintenance_context"]["is_current_revision"]
                    is False
                )
                assert "state_token" not in json.dumps(payload)
                return Completion(
                    {
                        "text": "The task is reopened. Its dates are unknown.",
                        "source_ids": [current_source],
                    },
                    1,
                    1,
                )

        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(actor, "ai", "openai", "Synthetic", "synthetic")
        vault.set_preferences(actor, True)
        provider = SourcedProvider()
        app.state.chat_provider = provider
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        payload = {
            "mode": "ask",
            "request_id": "task-recall",
            "text": "Was Obsoletemarker completed?",
            "model": "synthetic",
            "credential_id": credential.id,
        }
        path = f"/api/chat/conversations/{conversation}/turns"
        response = client.post(path, headers=alice, json=payload).json()
        assert response["state"] == "complete"
        assert response["result"]["sources"][0]["id"] == current_source
        assert provider.calls == 2
        assert client.post(path, headers=alice, json=payload).json() == response
        assert provider.calls == 2


def test_keyword_recall_follows_completed_statement_to_reopened_unknown_dates(
    tmp_path: Path,
) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    tasks = MaintenanceService(store.engine)
    created = tasks.create(alice, plan(vehicle))
    task = tasks.get(alice, created["id"])
    tasks.revise(
        alice,
        change(
            task,
            "completed",
            state="completed",
            completed_on="2026-10-19",
            text="Obsoleteuniqueword: I thought this was completed.",
        ),
    )
    completed = tasks.get(alice, created["id"])
    tasks.revise(
        alice,
        change(
            completed,
            "reopened",
            state="open",
            due_on=None,
            completed_on=None,
            text="I reopened the task. Both dates are unknown.",
        ),
    )
    current = tasks.get(alice, created["id"])
    chat = ChatService(store.engine)
    evidence = chat.evidence(alice, "Obsoleteuniqueword")
    assert evidence[0]["id"] == current["revision"]["source_id"]
    old = next(
        row for row in evidence if row["id"] == completed["revision"]["source_id"]
    )
    metadata = old["maintenance_context"]
    assert metadata["is_current_revision"] is False
    assert metadata["state"] == "completed"
    assert metadata["current_source_id"] == current["revision"]["source_id"]
    assert metadata["entity_id"] == vehicle
    head = evidence[0]["maintenance_context"]
    assert head["is_current_revision"] is True and head["state"] == "open"
    assert head["due_on"] is None and head["completed_on"] is None
    assert head["read_at"] >= head["recorded_at"]
    assert chat.evidence(bob, "Obsoleteuniqueword") == []
    assert tasks.source_context(bob, old["id"]) is None
    assert MemoryService(store.engine).get_source(alice, old["id"]).text == old["text"]
    context = RecallTools(chat).collect(
        alice,
        RecallPlan(
            query="Obsoleteuniqueword", entity_names=[], include_connections=False
        ),
    )
    assert context["evidence"][0]["id"] == evidence[0]["id"]
    assert "state_token" not in json.dumps(context)
    assert "request_id" not in json.dumps(context)


@pytest.mark.parametrize("state", ["open", "completed", "canceled"])
def test_typed_source_context_requires_actual_owned_revision(
    tmp_path: Path,
    state: str,
) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    tasks = MaintenanceService(store.engine)
    created = tasks.create(alice, plan(vehicle, state=state, due_on=None))
    task = tasks.get(alice, created["id"])
    source_id = task["revision"]["source_id"]
    context = tasks.source_context(alice, source_id)
    assert context is not None
    assert context["state"] == state and context["completed_on"] is None
    assert context["revision_id"] == context["current_revision_id"]
    assert context["source_id"] == context["current_source_id"]
    assert context["target"] == task["target"]
    assert tasks.source_context(bob, source_id) is None
    memory = MemoryService(store.engine)
    spoof = memory.ingest(
        alice,
        SourceInput(
            text="Fake maintenance statement", namespace="maintenance-revisions"
        ),
    )
    assert tasks.source_context(alice, spoof.id) is None
    assert "maintenance_context" not in ChatService(store.engine).source_metadata(
        alice, spoof
    )


def test_maintenance_recall_keeps_current_before_history_with_small_budget(
    tmp_path: Path,
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    tasks = MaintenanceService(store.engine)
    created = tasks.create(alice, plan(vehicle, text="Longobsolete " + "x" * 3500))
    old = tasks.get(alice, created["id"])
    tasks.revise(alice, change(old, "cancel", state="canceled", due_on=None))
    current = tasks.get(alice, created["id"])
    tools = RecallTools(ChatService(store.engine))
    context: dict[str, Any] = tools.collect(
        alice,
        RecallPlan(query="Longobsolete", entity_names=[], include_connections=False),
        max_bytes=2000,
    )
    assert len(json.dumps(context, ensure_ascii=False).encode()) <= 2000
    assert len(context["evidence"]) <= 8 and context["truncated"]
    for row in context["evidence"]:
        meta = row["maintenance_context"]
        if not meta["is_current_revision"]:
            assert any(
                source["id"] == meta["current_source_id"]
                for source in context["evidence"]
            )
    assert context["evidence"][0]["id"] == current["revision"]["source_id"]


def test_following_old_task_matches_never_exceeds_eight_sources(tmp_path: Path) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    tasks = MaintenanceService(store.engine)
    for index in range(6):
        created = tasks.create(
            alice,
            plan(
                vehicle,
                request_id=f"create-{index}",
                title=f"Task {index}",
                text="Obsoletecap statement.",
            ),
        )
        old = tasks.get(alice, created["id"])
        tasks.revise(
            alice,
            change(old, f"cancel-{index}", state="canceled", text="Changed plan."),
        )
    chat = ChatService(store.engine)
    keyword = chat.evidence(alice, "Obsoletecap")
    recalled = RecallTools(chat).collect(
        alice,
        RecallPlan(query="Obsoletecap", entity_names=[], include_connections=False),
    )
    for rows in (keyword, recalled["evidence"]):
        assert len(rows) == 8
        identifiers = {row["id"] for row in rows}
        assert rows[0]["maintenance_context"]["is_current_revision"]
        for row in rows:
            if not row["maintenance_context"]["is_current_revision"]:
                assert row["maintenance_context"]["current_source_id"] in identifiers
    assert recalled["truncated"]
