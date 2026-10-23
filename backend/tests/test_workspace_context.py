from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from test_reconciliation import setup

from lifegather.chat.context import ContextRead, ContextRef, WorkspaceContexts
from lifegather.chat.organizer import OrganizationAction, WorkspaceOrganizer
from lifegather.memory.service import MemoryError
from lifegather.profiles.service import ProfileCreate, ProfileService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_domain_change_rolls_back_if_reply_fails_and_concurrent_retry_saves_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lifegather.chat.service import ChatService, TurnInput

    auth, actor, _, _, _ = setup(tmp_path)
    profiles = ProfileService(auth.engine)
    truck = profiles.create(
        actor,
        ProfileCreate(
            name="Synthetic F150",
            kind="vehicle",
            text="Synthetic",
            operation_key="truck",
        ),
    )
    chat = ChatService(auth.engine)
    conversation = chat.create(actor)["id"]
    snapshot = WorkspaceContexts(auth.engine).read(
        actor, ContextRead(page="Assets", entity_id=truck.id)
    )
    data = TurnInput(
        request_id="atomic",
        mode="organize",
        text="Set model to F150",
        context=ContextRef(
            page="Assets", entity_id=truck.id, version=snapshot["version"]
        ),
    )
    chat.begin(actor, conversation, data)
    original = WorkspaceOrganizer.execute_in

    def fail_after_write(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise MemoryError("Synthetic failure before saving reply")

    with monkeypatch.context() as patch:
        patch.setattr(WorkspaceOrganizer, "execute_in", fail_after_write)
        with pytest.raises(MemoryError):
            chat.organize(actor, conversation, data)
    assert not any(
        row.predicate == "profile_model"
        for row in profiles.get(actor, truck.id)["facts"]
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: chat.organize(actor, conversation, data), range(2))
        )
    assert results[0] and results[0] == results[1] and results[0]["state"] == "complete"
    assert (
        len(
            [
                row
                for row in profiles.get(actor, truck.id)["facts"]
                if row.predicate == "profile_model"
            ]
        )
        == 1
    )
    auth.engine.dispose()


def test_chat_edits_commit_with_the_reply_replay_and_cancellation(
    tmp_path: Path,
) -> None:
    from lifegather.chat.recall import RecallPlan, RecallTools
    from lifegather.chat.service import ChatService, TurnInput

    auth, actor, bob, _, _ = setup(tmp_path)
    profiles = ProfileService(auth.engine)
    truck = profiles.create(
        actor,
        ProfileCreate(
            name="Synthetic F150",
            kind="vehicle",
            text="Synthetic owned truck",
            operation_key="truck",
        ),
    )
    chat = ChatService(auth.engine)
    conversation = chat.create(actor)["id"]
    snap = WorkspaceContexts(auth.engine).read(
        actor, ContextRead(page="Assets", entity_id=truck.id)
    )
    context = ContextRef(page="Assets", entity_id=truck.id, version=snap["version"])
    waiting = TurnInput(
        request_id="waiting", mode="organize", text="Add a VIN number", context=context
    )
    chat.begin(actor, conversation, waiting)
    waiting_result = chat.organize(actor, conversation, waiting)
    assert (
        waiting_result and waiting_result["result"]["awaiting"]["entity_id"] == truck.id
    )
    data = TurnInput(
        request_id="vin", mode="organize", text="1FTFW1E50NFA00001", context=context
    )
    chat.begin(actor, conversation, data)
    saved = chat.organize(actor, conversation, data)
    assert saved and saved["state"] == "complete"
    assert chat.organize(actor, conversation, data) == saved
    assert (
        len(
            [
                row
                for row in profiles.get(actor, truck.id)["facts"]
                if row.predicate == "profile_vin"
            ]
        )
        == 1
    )
    recall = RecallTools(chat).collect(
        actor,
        RecallPlan(query="unmatched", entity_names=[], include_connections=False),
        pinned_entity_id=truck.id,
    )
    assert recall["records"][0]["entity"]["id"] == truck.id
    assert recall["records"][0]["facts"]
    with pytest.raises(MemoryError):
        RecallTools(chat).collect(
            bob,
            RecallPlan(query="truck", entity_names=[], include_connections=False),
            pinned_entity_id=truck.id,
        )
    fresh = WorkspaceContexts(auth.engine).read(
        actor, ContextRead(page="Assets", entity_id=truck.id)
    )
    canceled = TurnInput(
        request_id="canceled",
        mode="organize",
        text="Set model to Changed",
        context=ContextRef(page="Assets", entity_id=truck.id, version=fresh["version"]),
    )
    chat.begin(actor, conversation, canceled)
    chat.cancel(actor, canceled.request_id)
    canceled_result = chat.organize(actor, conversation, canceled)
    assert canceled_result and canceled_result["state"] == "canceled"
    assert not any(
        row.predicate == "profile_model"
        for row in profiles.get(actor, truck.id)["facts"]
    )
    auth.engine.dispose()


def test_http_and_mcp_context_require_the_callers_private_record() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        owner, actor = signed_headers(app, "context-owner")
        foreign, _ = signed_headers(app, "context-foreign")
        truck = ProfileService(app.state.auth_store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic F150",
                kind="vehicle",
                text="Synthetic test",
                operation_key="truck",
            ),
        )
        body = {"page": "Assets", "entity_id": truck.id}
        assert client.post("/api/chat/context", json=body).status_code == 401
        assert (
            client.post("/api/chat/context", headers=foreign, json=body).status_code
            == 400
        )
        snapshot = client.post("/api/chat/context", headers=owner, json=body).json()
        result = rpc(client, owner, "workspace_context_get", body).json()["result"]
        assert result["structuredContent"] == snapshot
        assert rpc(client, foreign, "workspace_context_get", body).json()["result"][
            "isError"
        ]
        action = {
            "request_id": "mcp-vin",
            "text": "Set VIN to 1FTFW1E50NFA00001",
            "context": {**body, "version": snapshot["version"]},
        }
        assert (
            not rpc(client, owner, "workspace_organize", action)
            .json()["result"]
            .get("isError")
        )
        conversation = client.post("/api/chat/conversations", headers=owner).json()[
            "id"
        ]
        path = f"/api/chat/conversations/{conversation}/turns"
        request = {"request_id": "open", "text": "Edit my F150", "mode": "organize"}
        assert (
            client.post(
                path, headers={"Cookie": owner["Cookie"]}, json=request
            ).status_code
            == 403
        )
        response = client.post(path, headers=owner, json=request).json()
        assert response["result"]["navigation"]["entity_id"] == truck.id
        assert client.post(path, headers=owner, json=request).json() == response


def test_contextual_vin_is_scoped_sourced_idempotent_and_conflict_checked(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    truck = ProfileService(auth.engine).create(
        actor,
        ProfileCreate(
            name="Ford F-150",
            kind="vehicle",
            text="My synthetic truck",
            operation_key="truck",
        ),
    )
    service = WorkspaceContexts(auth.engine)
    snapshot = service.read(actor, ContextRead(page="Assets", entity_id=truck.id))
    context = ContextRef(page="Assets", entity_id=truck.id, version=snapshot["version"])
    organizer = WorkspaceOrganizer(auth.engine)
    waiting = organizer.run(
        actor,
        OrganizationAction(request_id="ask", text="Add a VIN number", context=context),
    )
    assert waiting["awaiting"]["field"] == "vin"
    assert waiting["awaiting"]["entity_id"] == truck.id
    data = OrganizationAction(
        request_id="save", text="Set VIN to 1FTFW1E50NFA00001", context=context
    )
    saved = organizer.run(actor, data)
    assert saved["changed_entity_id"] == truck.id
    assert saved == organizer.run(actor, data)
    profile = ProfileService(auth.engine).get(actor, truck.id)
    fact = next(row for row in profile["facts"] if row.predicate == "profile_vin")
    assert fact.status == "stated" and fact.value == "1FTFW1E50NFA00001"
    assert (
        memory.get_source(actor, str(fact.evidence[0]["source_id"])).text == data.text
    )
    with pytest.raises(MemoryError):
        organizer.run(
            actor,
            OrganizationAction(
                request_id="stale", text="Set VIN to changed", context=context
            ),
        )
    with pytest.raises(MemoryError):
        service.read(bob, ContextRead(page="Assets", entity_id=truck.id))
    auth.engine.dispose()


def test_explicit_navigation_resolves_unique_records_and_never_guesses_duplicates(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    profiles = ProfileService(auth.engine)
    first = profiles.create(
        actor,
        ProfileCreate(
            name="Ford F-150",
            kind="vehicle",
            text="Synthetic first truck",
            operation_key="first",
        ),
    )
    organizer = WorkspaceOrganizer(auth.engine)
    action = OrganizationAction(request_id="open", text="I want to edit my F150")
    result = organizer.run(actor, action)
    assert result["navigation"]["entity_id"] == first.id
    assert organizer.run(bob, action).get("navigation") is None
    second = profiles.create(
        actor,
        ProfileCreate(
            name="Ford F-150",
            kind="vehicle",
            text="Synthetic second truck",
            operation_key="second",
        ),
    )
    ambiguous = organizer.run(
        actor, OrganizationAction(request_id="ambiguous", text="Edit my F150")
    )
    assert ambiguous.get("navigation") is None
    assert {row["id"] for row in ambiguous["choices"]} == {first.id, second.id}
    assert (
        organizer.run(
            actor,
            OrganizationAction(
                request_id="quote", text='An email says "edit my F150". Is that safe?'
            ),
        ).get("navigation")
        is None
    )
    auth.engine.dispose()
