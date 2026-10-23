from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import database, restore_copy
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_asset_proposals import review, setup
from test_mcp_http import rpc, signed_headers

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.models import AssetAction
from lifegather.assets.service import AssetList, AssetRead, AssetService
from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService

pytestmark = pytest.mark.usefixtures("configured_database")


def prepared(tmp_path: Path) -> tuple[Any, ...]:
    auth, alice, bob, memory, original, proposals, proposal = setup(tmp_path)
    accepted = proposals.review(alice, review(proposal["id"]))
    return (
        auth,
        alice,
        bob,
        memory,
        original,
        accepted["result"],
        ActionService(auth.engine),
    )


def change(asset_id: str, **extra: Any) -> AssetChange:
    return AssetChange.model_validate(
        {
            "asset_id": asset_id,
            "request_id": "sold",
            "operation": "ownership",
            "status": "sold",
            "note": "I sold this item.",
            "event_date": "2024-05-04",
            **extra,
        }
    )


def test_ownership_intervals_history_replay_and_restore(tmp_path: Path) -> None:
    auth, alice, bob, memory, original, discovery, actions = prepared(tmp_path)
    identifier = discovery["asset_ids"][0]
    sold = actions.apply(alice, change(identifier))
    from lifegather.chat.service import ChatService

    evidence = ChatService(auth.engine).evidence(alice, "trimmer")
    assert evidence[0]["asset_context"]["user_selected_status"] == "sold"
    assert evidence[0]["text"] == "I sold this item."
    assert AssetService(auth.engine).list(alice, AssetList())["items"] == []
    owned = actions.apply(
        alice,
        change(
            identifier,
            request_id="owned",
            expected_action_id=sold["id"],
            status="owned",
            note="I bought this item back.",
            event_date="2025-01-03",
        ),
    )
    assert (
        AssetService(auth.engine).list(alice, AssetList())["items"][0]["id"]
        == identifier
    )
    past = memory.facts(alice, identifier, world_date="2024-08-01")
    assert any(f.predicate == "owned" and f.value is False for f in past)
    assert any(
        f.predicate == "owned" and f.value is True
        for f in memory.facts(alice, identifier, world_date="2025-08-01")
    )
    assert actions.apply(alice, change(identifier)) == sold
    with pytest.raises(NoteConflict):
        actions.apply(alice, change(identifier, request_id="stale"))
    with pytest.raises(NoteConflict):
        actions.apply(alice, change(identifier, note="Changed replay"))
    with pytest.raises(MemoryError):
        actions.apply(bob, change(identifier))
    view = AssetService(auth.engine).get(alice, AssetRead(asset_id=identifier, limit=1))
    assert view["action_head"] == owned["id"] and len(view["actions"]) == 1
    assert (
        AssetService(auth.engine).get(
            alice,
            AssetRead(asset_id=identifier, action_cursor=view["next_action_cursor"]),
        )["actions"][0]["id"]
        == sold["id"]
    )
    assert actions.export_page(bob)["items"] == []
    assert memory.get_source(alice, original.id).text == original.text
    backup = tmp_path / "restored.jsonl"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(restore_copy(backup))
    restored.migrate()
    assert (
        AssetService(restored.engine).get(
            alice, AssetRead(asset_id=identifier, limit=1)
        )
        == view
    )


def test_association_correction_then_undo_preserves_sources(tmp_path: Path) -> None:
    auth, alice, bob, memory, original, discovery, actions = prepared(tmp_path)
    identifier = discovery["asset_ids"][0]
    other_source = memory.ingest(
        alice, SourceInput(text="I own a different synthetic tool.")
    )
    other = ReconciliationService(auth.engine).discover(
        alice,
        DiscoveryInput(
            source_id=other_source.id,
            item_key="other",
            name="different synthetic tool",
            quantity=1,
            kind="possession",
            quote=other_source.text,
        ),
    )
    target = other.asset_ids[0]
    request = change(
        identifier,
        request_id="move",
        operation="reassociate",
        status=None,
        event_date=None,
        decision_id=discovery["decision_id"],
        target_asset_id=target,
        note="The note belongs to my other item.",
    )
    moved = actions.apply(alice, request)
    assert moved["decision"]["asset_ids"] == [target]
    assert actions.apply(alice, request) == moved
    assert (
        AssetService(auth.engine).get(alice, AssetRead(asset_id=identifier))[
            "in_inventory"
        ]
        is False
    )
    undo = actions.apply(
        alice,
        change(
            target,
            request_id="undo",
            operation="undo",
            status=None,
            event_date=None,
            decision_id=moved["decision"]["decision_id"],
            note="Undo the mistaken association.",
        ),
    )
    assert undo["decision"]["outcome"] == "create"
    assert (
        identifier in undo["decision"]["asset_ids"] or not undo["decision"]["asset_ids"]
    )
    assert memory.get_source(alice, original.id).text == original.text
    with pytest.raises(NoteConflict):
        actions.apply(alice, request.model_copy(update={"request_id": "stale-move"}))


def test_competing_actions_and_atomic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, alice, _, memory, _, discovery, actions = prepared(tmp_path)
    identifier = discovery["asset_ids"][0]

    def apply(index: int) -> str:
        try:
            return str(
                actions.apply(alice, change(identifier, request_id=f"compete-{index}"))[
                    "id"
                ]
            )
        except NoteConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(apply, range(4)))
    assert outcomes.count("conflict") == 3
    head = next(item for item in outcomes if item != "conflict")
    before = memory.export_page(alice, "sources")
    old = actions.memory._audit

    def fail(db: Any, actor: Any, operation: str, target: str, now: int) -> None:
        if operation == "asset_ownership":
            raise MemoryError("Synthetic failure")
        old(db, actor, operation, target, now)

    monkeypatch.setattr(actions.memory, "_audit", fail)
    with pytest.raises(MemoryError):
        actions.apply(
            alice,
            change(
                identifier,
                request_id="rollback",
                expected_action_id=head,
                status="owned",
                event_date="2025-01-01",
            ),
        )
    assert memory.export_page(alice, "sources") == before
    assert (
        AssetService(auth.engine).get(alice, AssetRead(asset_id=identifier))[
            "action_head"
        ]
        == head
    )
    with Session(auth.engine) as db:
        assert db.query(AssetAction).count() == 1


def test_http_mcp_authentication_and_bounds() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        memory = MemoryService(app.state.auth_store.engine)
        source = memory.ingest(actor, SourceInput(text="I own a synthetic drill."))
        discovery = ReconciliationService(memory.engine).discover(
            actor,
            DiscoveryInput(
                source_id=source.id,
                item_key="drill",
                name="synthetic drill",
                quantity=1,
                kind="possession",
                quote=source.text,
            ),
        )
        data = change(discovery.asset_ids[0]).model_dump()
        path = "/api/assets/actions"
        assert client.post(path, json=data).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": alice["Cookie"]}, json=data
            ).status_code
            == 403
        )
        assert client.post(path, headers=bob, json=data).status_code == 400
        assert (
            client.post(
                path, headers=alice, json={**data, "user_id": "foreign"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                path, headers=alice, json={**data, "event_date": "2099-01-01"}
            ).status_code
            == 422
        )
        assert client.post(path, headers=alice, content=b"x" * 33000).status_code == 413
        saved = rpc(client, alice, "asset_change", data).json()["result"][
            "structuredContent"
        ]
        assert client.post(path, headers=alice, json=data).json() == saved
        assert (
            client.post(
                path, headers=alice, json={**data, "request_id": "stale"}
            ).status_code
            == 409
        )


@pytest.mark.usefixtures("legacy_audit_writer")
def test_upgrade_keeps_existing_inventory_and_owner_foreign_keys(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    import lifegather

    store = AuthStore(database(tmp_path / "old", empty=True))
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0008_asset_proposals")
    signed = store.login("legacy", "legacy@example.test", "Legacy", now=100)
    memory = MemoryService(store.engine)
    source = memory.ingest(signed.user, SourceInput(text="I own a synthetic tool."))
    decision = ReconciliationService(store.engine).discover(
        signed.user,
        DiscoveryInput(
            source_id=source.id,
            item_key="old",
            name="synthetic tool",
            quantity=1,
            kind="possession",
            quote=source.text,
        ),
    )
    before = ReconciliationService(store.engine).inventory(signed.user)
    store.migrate()
    assert ReconciliationService(store.engine).inventory(signed.user) == before
    assert store.authenticate(signed.token, now=101) is not None
    bob = store.login("bob", "bob@example.test", "Bob", now=100).user
    bob_source = memory.ingest(bob, SourceInput(text="I own a separate tool."))
    bob_decision = ReconciliationService(store.engine).discover(
        bob,
        DiscoveryInput(
            source_id=bob_source.id,
            item_key="bob",
            name="separate tool",
            quantity=1,
            kind="possession",
            quote=bob_source.text,
        ),
    )
    with pytest.raises(IntegrityError), store.engine.begin() as connection:
        connection.execute(
            insert(AssetAction).values(
                id="foreign-source",
                user_id=bob.id,
                asset_id=bob_decision.asset_ids[0],
                source_id=source.id,
                request_id="attack",
                fingerprint="attack",
                operation="ownership",
                result_json="{}",
                recorded_at=1,
            )
        )
    result = ActionService(store.engine).apply(
        signed.user, change(decision.asset_ids[0])
    )
    assert result["status"] == "sold"
