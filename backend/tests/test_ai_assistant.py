from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from test_mcp_http import signed_headers

from lifegather.assets.manual import (
    ManualAssetCreate,
    ManualAssetFields,
    ManualAssets,
)
from lifegather.auth.store import Account
from lifegather.chat.assistant import AssistantStep
from lifegather.chat.provider import Completion
from lifegather.chat.service import ChatService
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.memory.schemas import FactView
from lifegather.profiles.service import ProfileChange, ProfileService

Script = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


def step(action: str, **values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "action": action,
        "query": None,
        "asset_id": None,
        "new_asset": None,
        "fields": [],
        "email_scan": None,
        "message": None,
        "choice_ids": [],
    }
    return {**base, **values}


def new_asset(name: str, quote: str, **values: Any) -> dict[str, Any]:
    return {
        "name": name,
        "manufacturer": None,
        "model": None,
        "serial": None,
        "ownership_quote": quote,
        "duplicate_choice": "none",
        "link_asset_id": None,
        **values,
    }


def field(name: str, value: str, custom: str | None = None) -> dict[str, Any]:
    return {"field": name, "custom_name": custom, "value": value}


class ScriptedProvider:
    """Plays model decisions in order; each may inspect the bounded payload."""

    def __init__(self) -> None:
        self.script: list[Script] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion:
        assert schema is AssistantStep
        self.calls.append(payload)
        planned = self.script.pop(0)
        value = planned(payload) if callable(planned) else planned
        return Completion(AssistantStep.model_validate(value).model_dump(), 10, 5)


@dataclass
class Case:
    client: TestClient
    headers: dict[str, str]
    actor: Account
    other: dict[str, str]
    other_actor: Account
    provider: ScriptedProvider
    credential: str
    engine: Any

    def conversation(self) -> str:
        response = self.client.post("/api/chat/conversations", headers=self.headers)
        return str(response.json()["id"])

    def send(
        self, conversation: str, key: str, text: str, *script: Script, **extra: Any
    ) -> dict[str, Any]:
        self.provider.script = list(script)
        response = self.client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=self.headers,
            json={
                "request_id": key,
                "mode": "assistant",
                "text": text,
                "credential_id": self.credential,
                "model": "fixture-model",
                **extra,
            },
        )
        assert response.status_code == 200, response.text
        assert self.provider.script == [], "unused scripted steps"
        result: dict[str, Any] = response.json()
        return result

    def asset(self, name: str, key: str, actor: Account | None = None) -> str:
        owner = actor or self.actor
        manual = ManualAssets(self.engine)
        preview = manual.preview(
            owner, ManualAssetFields(name=name, ownership_confirmed=True)
        )
        return str(
            manual.save(
                owner,
                ManualAssetCreate(
                    request_id=key,
                    name=name,
                    ownership_confirmed=True,
                    candidate_ids=[c["id"] for c in preview["candidates"]],
                ),
            )["asset"]["id"]
        )

    def facts(self, asset_id: str, *, history: bool = False) -> list[FactView]:
        facts: list[FactView] = ProfileService(self.engine).get(
            self.actor, asset_id, history=history
        )["facts"]
        return facts

    def current(self, asset_id: str) -> dict[str, Any]:
        return {
            fact.predicate: fact.value
            for fact in self.facts(asset_id)
            if fact.predicate != "profile_asset_type"
        }


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Case]:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    provider = ScriptedProvider()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, other_actor = signed_headers(app, "bob")
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
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        yield Case(
            client,
            alice,
            actor,
            bob,
            other_actor,
            provider,
            credential,
            app.state.auth_store.engine,
        )


def test_creates_owned_asset_with_details_then_updates_several_fields(
    case: Case,
) -> None:
    conversation = case.conversation()
    request = (
        "I own a Makita drill, model DHP484, serial 0012345. "
        "Its battery type is 18V LXT."
    )
    created = case.send(
        conversation,
        "create",
        request,
        step("search_assets", query="Makita drill"),
        lambda payload: (
            step(
                "create_asset",
                new_asset=new_asset(
                    "Makita drill",
                    "I own",
                    manufacturer="Makita",
                    model="DHP484",
                    serial="0012345",
                ),
                fields=[field("custom", "18V LXT", "Battery type")],
            )
            if payload["steps"][0]["result"]["assets"] == []
            else pytest.fail("unexpected search result")
        ),
    )
    assert created["state"] == "complete", created
    result = created["result"]
    asset_id = result["changed_entity_id"]
    assert result["navigation"]["entity_id"] == asset_id
    assert result["assistant"]["operation"] == "create"
    assert "Added Makita drill" in result["text"]
    assert case.current(asset_id) == {
        "profile_manufacturer": "Makita",
        "profile_model": "DHP484",
        "profile_serial": "0012345",
        "profile_custom_battery_type": "18V LXT",
    }
    # The user's own wording is saved as the evidence, labeled as AI-assisted.
    assert any(request in source["text"] for source in result["sources"])
    assert all(
        "Makita" not in s["text"] or request in s["text"] for s in result["sources"]
    )

    # Replaying the same request never calls the provider or writes again.
    calls = len(case.provider.calls)
    assert case.send(conversation, "create", request) == created
    assert len(case.provider.calls) == calls

    # A later conversation updates and corrects several fields in one request.
    later = case.conversation()
    update = "My Makita drill's battery type is 18V XGT and its paint is teal."
    updated = case.send(
        later,
        "update",
        update,
        step("search_assets", query="Makita"),
        step("read_asset", asset_id=asset_id),
        lambda payload: (
            step(
                "update_asset",
                asset_id=asset_id,
                fields=[
                    field("custom", "18V XGT", "Battery type"),
                    field("paint", "teal"),
                ],
            )
            if payload["steps"][1]["result"]["details"]["custom_battery_type"]["values"]
            == ["18V LXT"]
            else pytest.fail("current details not supplied")
        ),
    )
    assert updated["state"] == "complete", updated
    saved = updated["result"]["assistant"]["saved_fields"]
    assert [(item["field"], item["replaced"]) for item in saved] == [
        ("battery type", True),
        ("paint", False),
    ]
    assert case.current(asset_id)["profile_custom_battery_type"] == "18V XGT"
    assert case.current(asset_id)["profile_paint"] == "teal"
    history = [
        fact.value
        for fact in case.facts(asset_id, history=True)
        if fact.predicate == "profile_custom_battery_type"
    ]
    assert history == ["18V LXT", "18V XGT"]
    assert [s["text"] for s in updated["result"]["sources"]] == [update, update]


def test_invented_value_or_partial_conflict_saves_nothing(case: Case) -> None:
    asset_id = case.asset("Shop vacuum", "vac")
    ProfileService(case.engine).save(
        case.actor,
        ProfileChange(
            entity_id=asset_id,
            field="paint",
            value="red",
            text="paint red",
            operation_key="one",
        ),
    )
    ProfileService(case.engine).save(
        case.actor,
        ProfileChange(
            entity_id=asset_id,
            field="paint",
            value="blue",
            text="paint blue",
            operation_key="two",
        ),
    )
    before = case.facts(asset_id, history=True)
    conversation = case.conversation()
    text = "Set my shop vacuum filter to HEPA-12 and paint to green."
    invented = case.send(
        conversation,
        "invented",
        text,
        step("search_assets", query="shop vacuum"),
        step(
            "update_asset",
            asset_id=asset_id,
            fields=[field("filter_dimensions", "HEPA 12 inch")],
        ),
        lambda payload: (
            step("answer", message="I need the exact filter size.")
            if "does not appear exactly" in payload["steps"][-1]["error"]
            else pytest.fail("missing validation feedback")
        ),
    )
    assert invented["result"]["text"].endswith("No changes were saved.")
    # A valid field is not saved when another field in the request conflicts.
    conflict = case.send(
        conversation,
        "conflict",
        text,
        step("search_assets", query="shop vacuum"),
        step(
            "update_asset",
            asset_id=asset_id,
            fields=[field("filter_dimensions", "HEPA-12"), field("paint", "green")],
        ),
    )
    assert "several current paint statements" in conflict["result"]["text"]
    assert case.facts(asset_id, history=True) == before


def test_ownership_and_unknown_ids_are_refused(case: Case) -> None:
    foreign = case.asset("Bob ladder", "ladder", case.other_actor)
    conversation = case.conversation()
    unowned = case.send(
        conversation,
        "unowned",
        "Add a Stihl chainsaw, model MS 250.",
        step(
            "create_asset",
            new_asset=new_asset(
                "Stihl chainsaw", "I own", manufacturer="Stihl", model="MS 250"
            ),
        ),
        step("read_asset", asset_id=foreign),
        step("update_asset", asset_id=foreign, fields=[field("paint", "MS 250")]),
        lambda payload: (
            step("clarify", message="Do you currently own it?")
            if [s["error"][:12] for s in payload["steps"]]
            == ["ownership_qu", "Unknown asse", "Unknown asse"]
            else pytest.fail(str(payload["steps"]))
        ),
    )
    assert unowned["result"]["assistant_pending"]["kind"] == "clarify"
    assert ProfileService(case.engine).get(case.other_actor, foreign)["facts"] == []
    listed = case.client.get("/api/assets", headers=case.headers).json()
    assert [item["name"] for item in listed["items"]] == []

    # The follow-up answer supplies ownership; the original turn is evidence.
    answered = case.send(
        conversation,
        "owned",
        "Yes, it's mine.",
        lambda payload: (
            step(
                "create_asset",
                new_asset=new_asset(
                    "Stihl chainsaw", "it's mine", manufacturer="Stihl", model="MS 250"
                ),
            )
            if payload["origin_user_messages"]
            == ["Add a Stihl chainsaw, model MS 250."]
            else pytest.fail("origin missing")
        ),
    )
    assert answered["result"]["assistant"]["operation"] == "create"
    assert case.current(answered["result"]["changed_entity_id"])["profile_model"] == (
        "MS 250"
    )


def test_duplicate_question_resolves_only_in_its_conversation(case: Case) -> None:
    existing = case.asset("Lawn mower", "mower")
    conversation = case.conversation()
    asked = case.send(
        conversation,
        "dupe",
        "I own a lawn mower.",
        step("create_asset", new_asset=new_asset("lawn mower", "I own")),
    )
    assert asked["result"]["choices"] == [{"id": existing, "name": "Lawn mower"}]
    assert asked["result"]["assistant_pending"]["candidate_ids"] == [existing]

    elsewhere = case.conversation()
    refused = case.send(
        elsewhere,
        "elsewhere",
        "I own a lawn mower, a different one.",
        step(
            "create_asset",
            new_asset=new_asset(
                "lawn mower", "I own", duplicate_choice="new", link_asset_id=None
            ),
        ),
        step("answer", message="Okay."),
    )
    assert "assistant" not in refused["result"]

    distinct = case.send(
        conversation,
        "distinct",
        "It's a different one.",
        lambda payload: (
            step(
                "create_asset",
                new_asset=new_asset("lawn mower", "I own", duplicate_choice="new"),
            )
            if payload["pending_question"]["candidates"]
            == [{"id": existing, "name": "Lawn mower"}]
            else pytest.fail("pending duplicate not supplied")
        ),
    )
    created = distinct["result"]["changed_entity_id"]
    assert created != existing
    names = [
        item["name"]
        for item in case.client.get("/api/assets", headers=case.headers).json()["items"]
    ]
    assert sorted(names) == ["Lawn mower", "lawn mower"]

    # The question is consumed: another "different one" asks again.
    again = case.send(
        conversation,
        "again",
        "Another different one.",
        step(
            "create_asset",
            new_asset=new_asset("lawn mower", "I own", duplicate_choice="new"),
        ),
        step("answer", message="Which mower?"),
    )
    assert "assistant" not in again["result"]


def test_same_name_choice_and_stale_record_refusal(case: Case) -> None:
    first = case.asset("Truck", "truck-1")
    second = case.asset("Truck", "truck-2")
    conversation = case.conversation()
    asked = case.send(
        conversation,
        "which",
        "The tire size on my truck is 265/70R17.",
        step("search_assets", query="truck"),
        step("clarify", message="Which truck?", choice_ids=sorted([first, second])),
    )
    assert {c["id"] for c in asked["result"]["choices"]} == {first, second}

    def modify(payload: dict[str, Any]) -> dict[str, Any]:
        ProfileService(case.engine).save(
            case.actor,
            ProfileChange(
                entity_id=second,
                field="paint",
                value="white",
                text="paint white",
                operation_key="race",
            ),
        )
        return step(
            "update_asset",
            asset_id=second,
            fields=[field("custom", "265/70R17", "Tire size")],
        )

    stale = case.send(
        conversation,
        "stale",
        "The second one.",
        step("read_asset", asset_id=second),
        modify,
    )
    assert "changed since it was read" in stale["result"]["text"]
    assert "profile_custom_tire_size" not in case.current(second)

    # A refused write does not leave the earlier choice open for reuse.
    saved = case.send(
        conversation,
        "saved",
        "The second one, please.",
        step(
            "update_asset",
            asset_id=second,
            fields=[field("custom", "265/70R17", "Tire size")],
        ),
        lambda payload: (
            step("answer", message="Please name the truck again.")
            if payload["steps"][0]["error"].startswith("Unknown asset ID")
            else pytest.fail("stale pending identity was reused")
        ),
    )
    # The refused turn completed without a pending question, so it is consumed.
    assert saved["state"] == "complete"
    assert "assistant" not in saved["result"]


def test_step_limit_and_cancellation_before_commit(case: Case) -> None:
    asset_id = case.asset("Kayak", "kayak")
    conversation = case.conversation()
    limited = case.send(
        conversation,
        "limit",
        "What's on my kayak?",
        *[step("search_assets", query="kayak")] * 6,
    )
    assert "step limit" in limited["result"]["text"]

    def cancel(payload: dict[str, Any]) -> dict[str, Any]:
        ChatService(case.engine).cancel(case.actor, "cancel")
        return step("update_asset", asset_id=asset_id, fields=[field("paint", "red")])

    stopped = case.send(
        conversation,
        "cancel",
        "My kayak's paint is red.",
        step("search_assets", query="kayak"),
        cancel,
    )
    assert stopped["state"] == "canceled"
    assert case.current(asset_id) == {}


def test_assistant_requires_connection_and_keeps_question_only_reads(
    case: Case,
) -> None:
    conversation = case.conversation()
    missing = case.client.post(
        f"/api/chat/conversations/{conversation}/turns",
        headers=case.headers,
        json={"request_id": "x", "mode": "assistant", "text": "Hi"},
    )
    assert missing.status_code == 422
    asset_id = case.asset("Bicycle", "bike")
    ProfileService(case.engine).save(
        case.actor,
        ProfileChange(
            entity_id=asset_id,
            field="paint",
            value="green",
            text="paint green",
            operation_key="bike-paint",
        ),
    )
    answered = case.send(
        conversation,
        "question",
        "What color is my bicycle?",
        step("read_asset", asset_id=asset_id),
        step("answer", message="Your bicycle's paint is recorded as green."),
        context={"page": "Assets", "entity_id": asset_id},
    )
    assert answered["result"]["text"] == (
        "Your bicycle's paint is recorded as green. No changes were saved."
    )
    assert answered["result"]["read_trace"] == [
        {"tool": "read_asset", "asset_id": asset_id}
    ]
    assert case.provider.calls[0]["selected_record"] == {
        "id": asset_id,
        "name": "Bicycle",
    }


def test_step_schema_is_strict_for_all_provider_adapters() -> None:
    from lifegather.chat.claude import wire_schema

    schema = AssistantStep.model_json_schema()

    def objects(node: Any) -> Iterator[dict[str, Any]]:
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for child in node.values():
                yield from objects(child)
        elif isinstance(node, list):
            for child in node:
                yield from objects(child)

    found = list(objects(schema))
    assert len(found) == 4
    for node in found:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])
    assert wire_schema(schema)["properties"]["action"]
