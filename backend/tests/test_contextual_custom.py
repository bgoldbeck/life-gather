from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from database_support import database
from test_asset_consolidation import prepared

from lifegather.assets.consolidation import ReverseConsolidation
from lifegather.auth.store import Account, AuthStore
from lifegather.chat.context import ContextRead, ContextRef, WorkspaceContexts
from lifegather.chat.organizer import OrganizationAction, WorkspaceOrganizer
from lifegather.chat.service import ChatService, TurnInput
from lifegather.memory.schemas import FactView
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.profiles.service import ProfileChange, ProfileCreate, ProfileService


def context(store: AuthStore, actor: Account, entity: str) -> ContextRef:
    snapshot = WorkspaceContexts(store.engine).read(
        actor, ContextRead(page="Assets", entity_id=entity)
    )
    return ContextRef(page="Assets", entity_id=entity, version=snapshot["version"])


@dataclass
class Case:
    store: AuthStore
    actor: Account
    foreign: Account
    entity: str

    def action(self, text: str, key: str = "save") -> OrganizationAction:
        return OrganizationAction(
            request_id=key,
            text=text,
            context=context(self.store, self.actor, self.entity),
        )

    def run(self, action: OrganizationAction) -> dict[str, Any]:
        return WorkspaceOrganizer(self.store.engine).run(self.actor, action)

    def facts(self, *, history: bool = False) -> list[FactView]:
        return cast(
            list[FactView],
            ProfileService(self.store.engine).get(
                self.actor, self.entity, history=history
            )["facts"],
        )


@pytest.fixture
def case(tmp_path: Path) -> Iterator[Case]:
    store = AuthStore(database(tmp_path))
    store.migrate()
    actor = store.login("alice", "alice@example.test", "Synthetic", now=1).user
    foreign = store.login("bob", "bob@example.test", "Synthetic", now=1).user
    entity = ProfileService(store.engine).create(
        actor,
        ProfileCreate(
            name="Synthetic car",
            kind="vehicle",
            text="Synthetic car",
            operation_key="car",
        ),
    )
    yield Case(store, actor, foreign, entity.id)
    store.engine.dispose()


def test_reversed_identity_does_not_replay_a_request_on_another_physical_item(
    tmp_path: Path,
) -> None:
    store, actor, _, _, _, records, service, request = prepared(tmp_path)
    organizer = WorkspaceOrganizer(store.engine)
    action = OrganizationAction(
        request_id="original",
        text='Set custom "Trim color" to Red',
        context=context(store, actor, records[1].id),
    )
    saved = organizer.run(actor, action)
    joined = service.apply(actor, request())
    service.reverse(
        actor,
        ReverseConsolidation(
            consolidation_id=joined["id"],
            request_id="reverse",
            note="Separate synthetic records.",
        ),
    )
    assert organizer.run(actor, action) == saved
    with pytest.raises(MemoryError, match="another record"):
        organizer.run(
            actor,
            action.model_copy(update={"context": context(store, actor, records[0].id)}),
        )
    store.engine.dispose()


def test_custom_http_and_mcp_share_owner_guards_and_invalid_turns_finish() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        owner, actor = signed_headers(app, "custom-owner")
        foreign, _ = signed_headers(app, "custom-foreign")
        store = app.state.auth_store
        car = ProfileService(store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="Synthetic car",
                operation_key="car",
            ),
        )
        action = {
            "request_id": "mcp-custom",
            "text": 'Set custom "Fuel type" to Regular',
            "context": context(store, actor, car.id).model_dump(),
        }
        result = rpc(client, owner, "workspace_organize", action).json()["result"]
        assert result["structuredContent"]["profile_fact_id"]
        assert (
            rpc(client, owner, "workspace_organize", action).json()["result"] == result
        )
        assert rpc(client, foreign, "workspace_organize", action).json()["result"][
            "isError"
        ]
        conversation = client.post("/api/chat/conversations", headers=owner).json()[
            "id"
        ]
        path = f"/api/chat/conversations/{conversation}/turns"
        fresh = context(store, actor, car.id).model_dump()
        invalid = {
            "request_id": "invalid-custom",
            "mode": "organize",
            "text": 'Set custom "VIN" to unsupported',
            "context": fresh,
        }
        failed = client.post(path, headers=owner, json=invalid)
        assert failed.status_code == 200 and failed.json()["state"] == "failed"
        assert "custom detail" in failed.json()["result"]["text"]
        assert client.post(path, headers=owner, json=invalid).json() == failed.json()
        valid = {
            **invalid,
            "request_id": "valid-custom",
            "text": 'Set custom "Tire size" to 205/55R16',
        }
        assert (
            client.post(
                path, headers={"Cookie": owner["Cookie"]}, json=valid
            ).status_code
            == 403
        )
        saved = client.post(path, headers=owner, json=valid)
        assert saved.status_code == 200 and saved.json()["state"] == "complete"
        assert saved.json()["result"]["profile_fact_id"]


def test_custom_commands_preserve_exact_evidence_history_and_replay(case: Case) -> None:
    action = case.action('Please set custom "Tire size" to 205/55R16')
    saved = case.run(action)
    assert saved["changed_entity_id"] == case.entity
    assert case.run(action) == saved
    fact = next(row for row in case.facts() if row.id == saved["profile_fact_id"])
    assert fact.predicate == "profile_custom_tire_size"
    assert fact.value == "205/55R16" and fact.status == "stated"
    source_id = fact.evidence[0]["source_id"]
    assert source_id is not None
    assert (
        MemoryService(case.store.engine).get_source(case.actor, source_id).text
        == action.text
    )
    stale = action.model_copy(
        update={"request_id": "stale", "text": 'Set custom "Tire size" to 215/55R16'}
    )
    with pytest.raises(MemoryError, match="changed"):
        case.run(stale)
    for text in (
        'Set custom "Fuel type" to 205/55R16',
        'Set custom "Tire size" to 215/55R16',
        'Record custom "tire-size" as 205/55R16',
    ):
        with pytest.raises(MemoryError):
            case.run(action.model_copy(update={"text": text}))
    corrected = case.run(
        case.action('Update custom "tire-size" to 215/55R16', "correct")
    )
    current = next(
        row for row in case.facts() if row.id == corrected["profile_fact_id"]
    )
    assert current.replaces_id == fact.id
    history = [
        row for row in case.facts(history=True) if row.predicate == fact.predicate
    ]
    assert {row.value for row in history} == {"205/55R16", "215/55R16"}
    assert len(history) == 2
    with pytest.raises(MemoryError):
        WorkspaceOrganizer(case.store.engine).run(case.foreign, action)


@pytest.mark.parametrize(
    "name",
    ["VIN", "filter dimensions", "profile-kind", "kind", "Tire/size", "Café", "x" * 49],
)
def test_custom_command_rejects_invalid_names_without_writing(
    case: Case, name: str
) -> None:
    with pytest.raises(MemoryError, match="custom detail"):
        case.run(case.action(f'Set custom "{name}" to supplied'))
    assert not any(row.predicate.startswith("profile_custom_") for row in case.facts())


def test_custom_commands_require_selected_record_and_explicit_value(case: Case) -> None:
    no_context = OrganizationAction(
        request_id="none", text='Set custom "Tire size" to 205/55R16'
    )
    assert "Open the item" in case.run(no_context)["text"]
    waiting = case.run(case.action('Add custom "Tire size"', "waiting"))
    assert "exact value" in waiting["text"]
    assert "205" not in waiting["text"]
    for index, text in enumerate(
        (
            'An email says: Set custom "Tire size" to 205/55R16',
            "205/55R16",
            "Set custom Tire size to 205/55R16",
            'Set custom "Tire size" to ' + "x" * 501,
        )
    ):
        assert "profile_fact_id" not in case.run(case.action(text, str(index)))
    assert not any(row.predicate.startswith("profile_custom_") for row in case.facts())


def test_multiple_current_custom_statements_require_review(case: Case) -> None:
    profiles = ProfileService(case.store.engine)
    for value in ("Red", "Blue"):
        profiles.save(
            case.actor,
            ProfileChange(
                entity_id=case.entity,
                field="custom",
                custom_name="Trim color",
                value=value,
                text=f"Synthetic {value}",
                operation_key=value,
            ),
        )
    with pytest.raises(MemoryError, match="Multiple current statements"):
        case.run(case.action('Set custom "Trim color" to Green'))
    assert (
        len(
            [
                row
                for row in case.facts()
                if row.predicate == "profile_custom_trim_color"
            ]
        )
        == 2
    )


def test_custom_chat_write_and_reply_are_atomic_cancellable_and_replayable(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = ChatService(case.store.engine)
    conversation = chat.create(case.actor)["id"]
    action = case.action('Set custom "Tire size" to 205/55R16')
    turn = TurnInput(mode="organize", **action.model_dump())
    chat.begin(case.actor, conversation, turn)
    original = WorkspaceOrganizer.execute_in

    def fail_after_write(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise MemoryError("Synthetic reply failure")

    with monkeypatch.context() as patch:
        patch.setattr(WorkspaceOrganizer, "execute_in", fail_after_write)
        with pytest.raises(MemoryError, match="reply failure"):
            chat.organize(case.actor, conversation, turn)
    assert not any(row.predicate.startswith("profile_custom_") for row in case.facts())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: chat.organize(case.actor, conversation, turn), range(2))
        )
    assert results[0] and results[0] == results[1] and results[0]["state"] == "complete"
    assert (
        len(
            [row for row in case.facts() if row.predicate == "profile_custom_tire_size"]
        )
        == 1
    )
    canceled = TurnInput(
        mode="organize",
        **case.action('Set custom "Fuel type" to Regular', "cancel").model_dump(),
    )
    chat.begin(case.actor, conversation, canceled)
    chat.cancel(case.actor, canceled.request_id)
    result = chat.organize(case.actor, conversation, canceled)
    assert result and result["state"] == "canceled"
    assert not any(row.predicate == "profile_custom_fuel_type" for row in case.facts())


@pytest.mark.parametrize("custom", [False, True])
def test_consolidated_corrections_retry_without_rewriting_original_subject(
    tmp_path: Path, custom: bool
) -> None:
    store, actor, _, _, source, records, service, request = prepared(tmp_path)
    profiles = ProfileService(store.engine)
    old = profiles.save(
        actor,
        ProfileChange(
            entity_id=records[1].id,
            field="custom" if custom else "paint",
            custom_name="Trim color" if custom else None,
            value="Red",
            text=source.text,
            operation_key="color",
        ),
    )
    joined = service.apply(actor, request())
    action = OrganizationAction(
        request_id="correct",
        text='Set custom "Trim color" to Blue' if custom else "Set paint to Blue",
        context=context(store, actor, records[0].id),
    )
    organizer = WorkspaceOrganizer(store.engine)
    result = organizer.run(actor, action)
    assert organizer.run(actor, action) == result
    fact = next(
        row
        for row in profiles.get(actor, records[0].id)["facts"]
        if row.id == result["profile_fact_id"]
    )
    assert fact.subject_id == records[1].id and fact.replaces_id == old.id
    with pytest.raises(MemoryError, match="changed"):
        service.reverse(
            actor,
            ReverseConsolidation(
                consolidation_id=joined["id"], request_id="reverse", note="Separate."
            ),
        )
    store.engine.dispose()
