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
from lifegather.assets.service import AssetList, AssetService
from lifegather.assets.types import STARTERS, AssetTypes, starter
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
        "asset_type_id": None,
        "fields": [],
        "email_scan": None,
        "maintenance": None,
        "maintenance_task_id": None,
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
    return {
        "field": name,
        "custom_name": custom,
        "type_field_id": None,
        "value": value,
    }


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
    assert len(found) == 6
    assert {"MaintenanceRequest", "MaintenanceField"} <= set(schema["$defs"])
    for node in found:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])
    assert wire_schema(schema)["properties"]["action"]


# Asset types and typed template fields ------------------------------------


def type_field(field_id: str, value: str) -> dict[str, Any]:
    return {**field("type_field", value), "type_field_id": field_id}


def listed(payload: dict[str, Any], name: str) -> dict[str, Any]:
    """A type from this request's list_asset_types result, by name."""
    for entry in payload["steps"]:
        for item in entry.get("result", {}).get("asset_types", []):
            if item["name"] == name:
                return dict(item)
    raise AssertionError(name)


def field_id(item: dict[str, Any], name: str) -> str:
    return str(next(f["type_field_id"] for f in item["fields"] if f["name"] == name))


def typed(case: Case, asset_id: str) -> tuple[list[Any], dict[str, Any]]:
    record = AssetTypes(case.engine).record(case.actor, asset_id)
    return (
        [row["value"] for row in record["assignments"]],
        {row["predicate"]: row["value"] for row in record["facts"]},
    )


def test_creates_typed_asset_and_recalls_fields_by_name(case: Case) -> None:
    conversation = case.conversation()
    request = (
        "I own a Honda Civic. It's a vehicle; tire size 205/55R16, year 2019, "
        "paint Sonic Gray."
    )

    def create(payload: dict[str, Any]) -> dict[str, Any]:
        vehicle = listed(payload, "Vehicle")
        return step(
            "create_asset",
            new_asset=new_asset("Honda Civic", "I own"),
            asset_type_id=vehicle["id"],
            fields=[
                type_field(field_id(vehicle, "Tire size"), "205/55R16"),
                type_field(field_id(vehicle, "Year"), "2019"),
                field("paint", "Sonic Gray"),
            ],
        )

    created = case.send(
        conversation, "civic", request, step("list_asset_types"), create
    )
    result = created["result"]
    assert "asset type (Vehicle)" in result["text"]
    assert "Tire size (205/55R16)" in result["text"]
    asset_id = result["assistant"]["asset_id"]
    assignments, facts = typed(case, asset_id)
    vehicle_id = starter(case.actor, *STARTERS[0])["id"]
    assert assignments == [vehicle_id]
    assert sorted(facts.values()) == ["2019", "205/55R16"]
    assert case.current(asset_id)["profile_paint"] == "Sonic Gray"
    assert len(result["sources"]) == 5
    texts = [source["text"] for source in result["sources"]]
    assert sum(request in text for text in texts) == 4  # entry, 2 type fields, paint
    assert any("to asset type " + vehicle_id in text for text in texts)

    def answer(payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload["steps"][-1]["result"]["asset_type"]
        sizes = next(f for f in summary["fields"] if f["name"] == "Tire size")
        assert summary["name"] == "Vehicle"
        assert sizes["values"] == ["205/55R16"]
        details = payload["steps"][-1]["result"]["details"]
        assert not any(name.startswith("template_") for name in details)
        return step("answer", message="Its tire size is 205/55R16.")

    recalled = case.send(
        case.conversation(),
        "recall",
        "What tire size does my Civic take?",
        step("search_assets", query="Civic"),
        lambda payload: step(
            "read_asset", asset_id=payload["steps"][-1]["result"]["assets"][0]["id"]
        ),
        answer,
    )
    assert "205/55R16" in recalled["result"]["text"]


def test_updates_type_and_several_type_fields_then_changes_type(case: Case) -> None:
    fridge = case.asset("Garage fridge", "fridge")
    conversation = case.conversation()
    request = (
        "My garage fridge is an appliance. Its filter specification is EDR1RXD1 "
        "and power requirements are 115V."
    )

    def update(payload: dict[str, Any]) -> dict[str, Any]:
        appliance = listed(payload, "Appliance")
        return step(
            "update_asset",
            asset_id=fridge,
            asset_type_id=appliance["id"],
            fields=[
                type_field(field_id(appliance, "Filter specification"), "EDR1RXD1"),
                type_field(field_id(appliance, "Power requirements"), "115V"),
            ],
        )

    case.send(
        conversation,
        "fridge-type",
        request,
        step("search_assets", query="fridge"),
        step("read_asset", asset_id=fridge),
        step("list_asset_types"),
        update,
    )
    appliance_id = starter(case.actor, *STARTERS[1])["id"]
    assignments, facts = typed(case, fridge)
    assert assignments == [appliance_id]
    assert sorted(facts.values()) == ["115V", "EDR1RXD1"]

    # Repeating the same type is unchanged; another named type replaces it.
    changed = case.send(
        conversation,
        "fridge-retype",
        "Actually file my garage fridge under electronics.",
        step("search_assets", query="fridge"),
        step("read_asset", asset_id=fridge),
        lambda payload: step(
            "update_asset",
            asset_id=fridge,
            asset_type_id=payload["steps"][-1]["result"]["asset_type"]["id"],
        ),
        step("list_asset_types"),
        lambda payload: step(
            "update_asset",
            asset_id=fridge,
            asset_type_id=listed(payload, "Electronics")["id"],
        ),
    )
    first_error = case.provider.calls[-1]["steps"][-2]["error"]
    assert "did not name the Appliance type" in first_error
    assert "asset type (Electronics)" in changed["result"]["text"]
    assert typed(case, fridge)[0] == [starter(case.actor, *STARTERS[2])["id"]]
    assignments_over_time = [
        str(fact.value)
        for fact in case.facts(fridge, history=True)
        if fact.predicate == "profile_asset_type"
    ]
    assert sorted(assignments_over_time) == sorted(
        [appliance_id, starter(case.actor, *STARTERS[2])["id"]]
    )


def test_invalid_type_requests_save_nothing(case: Case) -> None:
    other_vehicle = starter(case.other_actor, *STARTERS[0])["id"]
    conversation = case.conversation()

    def not_named(payload: dict[str, Any]) -> dict[str, Any]:
        return step(
            "create_asset",
            new_asset=new_asset("Honda Civic", "I own"),
            asset_type_id=listed(payload, "Vehicle")["id"],
        )

    def invented_value(payload: dict[str, Any]) -> dict[str, Any]:
        assert "did not name the Vehicle type" in payload["steps"][-1]["error"]
        return step(
            "create_asset",
            new_asset=new_asset("Honda Civic", "I own"),
            fields=[type_field("a" * 32, "225/45R17")],
        )

    def foreign_type(payload: dict[str, Any]) -> dict[str, Any]:
        assert "does not appear exactly" in payload["steps"][-1]["error"]
        return step(
            "create_asset",
            new_asset=new_asset("Honda Civic", "I own"),
            asset_type_id=other_vehicle,
        )

    def give_up(payload: dict[str, Any]) -> dict[str, Any]:
        assert "Unknown asset type ID" in payload["steps"][-1]["error"]
        return step("answer", message="Which type should I use?")

    reply = case.send(
        conversation,
        "bad-types",
        "I own a Honda Civic with tire size 205/55R16.",
        step("list_asset_types"),
        not_named,
        invented_value,
        foreign_type,
        give_up,
    )
    assert "No changes were saved" in reply["result"]["text"]
    assets = AssetService(case.engine).list(case.actor, AssetList(limit=8))
    assert assets["items"] == []


def test_wrong_type_field_rolls_back_assignment_and_new_asset(case: Case) -> None:
    def create(payload: dict[str, Any]) -> dict[str, Any]:
        furniture = listed(payload, "Furniture")
        vehicle = listed(payload, "Vehicle")
        return step(
            "create_asset",
            new_asset=new_asset("Oak desk", "I own"),
            asset_type_id=furniture["id"],
            fields=[
                type_field(field_id(furniture, "Material"), "oak"),
                type_field(field_id(vehicle, "Year"), "2019"),
            ],
        )

    def recover(payload: dict[str, Any]) -> dict[str, Any]:
        assert "not part of the Furniture type" in payload["steps"][-1]["error"]
        return step("answer", message="Year isn't a furniture detail.")

    case.send(
        case.conversation(),
        "desk",
        "I own an oak desk, furniture, material oak, bought 2019.",
        step("list_asset_types"),
        create,
        recover,
    )
    assets = AssetService(case.engine).list(case.actor, AssetList(limit=8))
    assert assets["items"] == []


def test_type_fields_need_an_assigned_type_and_vin_uses_standard_field(
    case: Case,
) -> None:
    truck = case.asset("Work truck", "truck")

    def without_type(payload: dict[str, Any]) -> dict[str, Any]:
        vehicle = listed(payload, "Vehicle")
        return step(
            "update_asset",
            asset_id=truck,
            fields=[type_field(field_id(vehicle, "Year"), "2015")],
        )

    def vin_field(payload: dict[str, Any]) -> dict[str, Any]:
        assert "Assign an asset type" in payload["steps"][-1]["error"]
        vehicle = listed(payload, "Vehicle")
        return step(
            "update_asset",
            asset_id=truck,
            asset_type_id=vehicle["id"],
            fields=[type_field(field_id(vehicle, "VIN"), "1FTFW1E50FFA00001")],
        )

    def standard(payload: dict[str, Any]) -> dict[str, Any]:
        assert "standard vin detail" in payload["steps"][-1]["error"]
        vehicle = listed(payload, "Vehicle")
        return step(
            "update_asset",
            asset_id=truck,
            asset_type_id=vehicle["id"],
            fields=[
                field("vin", "1FTFW1E50FFA00001"),
                type_field(field_id(vehicle, "Year"), "2015"),
            ],
        )

    saved = case.send(
        case.conversation(),
        "truck",
        "My work truck is a vehicle from 2015, VIN 1FTFW1E50FFA00001.",
        step("search_assets", query="truck"),
        step("list_asset_types"),
        without_type,
        vin_field,
        standard,
    )
    assert saved["result"]["assistant"]["operation"] == "update"
    assert case.current(truck)["profile_vin"] == "1FTFW1E50FFA00001"
    _, facts = typed(case, truck)
    assert "2015" in facts.values()
