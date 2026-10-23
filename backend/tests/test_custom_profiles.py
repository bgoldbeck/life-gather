import json
from datetime import date
from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from lifegather.assets.consolidation import Consolidate, ConsolidationService
from lifegather.auth.store import AuthStore
from lifegather.chat.context import ContextRead, WorkspaceContexts
from lifegather.config import Settings
from lifegather.main import create_app
from lifegather.memory.export import RecordExport
from lifegather.memory.history import FieldHistory, FieldHistoryRead
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.profiles.service import ProfileChange, ProfileCreate, ProfileService
from lifegather.recovery.bundle import RecoveryService

pytestmark = pytest.mark.usefixtures("configured_database")


def change(entity: str, **values: object) -> ProfileChange:
    return ProfileChange.model_validate(
        {
            "entity_id": entity,
            "field": "custom",
            "custom_name": "Fuel type",
            "value": "Regular",
            "text": "Synthetic manual says fuel type Regular.",
            "operation_key": "fuel",
            **values,
        }
    )


@pytest.mark.parametrize(
    "name",
    [
        None,
        " ",
        "x" * 49,
        "Tire/size",
        "Café",
        "_fuel",
        "fuel-",
        "VIN",
        "filter dimensions",
        "MODEL",
        "profile-kind",
        "kind",
    ],
)
def test_custom_names_refuse_invalid_and_reserved_identity_fields(
    name: str | None,
) -> None:
    with pytest.raises(ValidationError):
        change("entity", custom_name=name)
    with pytest.raises(ValidationError):
        change("entity", field="model", custom_name="Fuel type")


def test_custom_detail_preserves_sources_unknowns_history_and_private_replay(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    alice = store.login("a", "a@example.test", "Synthetic A", now=1).user
    bob = store.login("b", "b@example.test", "Synthetic B", now=1).user
    profiles = ProfileService(store.engine)
    car = profiles.create(
        alice,
        ProfileCreate(
            name="Synthetic car",
            kind="vehicle",
            text="Synthetic car record.",
            operation_key="car",
        ),
    )
    original = change(car.id, custom_name=" Fuel--TYPE ", valid_from=date(2025, 1, 1))
    first = profiles.save(alice, original)
    assert first.predicate == "profile_custom_fuel_type"
    assert original.custom_name == "fuel_type"
    assert profiles.save(alice, original).id == first.id
    source_id = first.evidence[0]["source_id"]
    assert source_id is not None
    assert (
        MemoryService(store.engine).get_source(alice, source_id).text == original.text
    )
    with pytest.raises(MemoryError):
        profiles.save(bob, original)
    with pytest.raises(MemoryError):
        profiles.get(bob, car.id)
    corrected = profiles.save(
        alice,
        change(
            car.id,
            value=None,
            status="unknown",
            text="Synthetic fuel type is unknown.",
            replaces_id=first.id,
            operation_key="unknown",
            valid_from=date(2026, 1, 1),
        ),
    )
    assert corrected.value is None and corrected.status == "unknown"
    before = len(profiles.get(alice, car.id, history=True)["facts"])
    for invalid in (
        change(
            car.id,
            custom_name="Tire size",
            replaces_id=corrected.id,
            operation_key="rename",
        ),
        change(
            car.id,
            value="Premium",
            text="Synthetic fuel type Premium.",
            operation_key="fuel",
        ),
    ):
        with pytest.raises(MemoryError):
            profiles.save(alice, invalid)
    assert len(profiles.get(alice, car.id, history=True)["facts"]) == before
    history = FieldHistory(store.engine).get(
        alice,
        FieldHistoryRead(
            entity_id=car.id,
            field=first.predicate,
        ),
    )
    assert [item["value"] for item in history["items"]] == ["Regular", None]
    context = WorkspaceContexts(store.engine).read(
        alice,
        ContextRead(
            page="Profiles",
            entity_id=car.id,
        ),
    )
    assert context["fields"]["custom_fuel_type"]["statements"][0]["id"] == corrected.id
    with pytest.raises(ValidationError):
        change(car.id, text="The exact value is absent.")
    with pytest.raises(ValidationError):
        change(car.id, value=None)
    with pytest.raises(ValidationError):
        change(car.id, valid_from=date(2026, 1, 2), valid_to=date(2026, 1, 1))


def test_custom_details_follow_consolidated_history_export_and_recovery(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "source"
    store = AuthStore(database(directory))
    store.migrate()
    actor = store.login("owner", "owner@example.test", "Synthetic", now=1).user
    profiles = ProfileService(store.engine)
    pair = [
        profiles.create(
            actor,
            ProfileCreate(
                name=name,
                kind="vehicle",
                text="Synthetic separate record.",
                operation_key=name,
            ),
        )
        for name in ("Manual car", "Receipt car")
    ]
    first = profiles.save(
        actor, change(pair[1].id, value="雪", text="Synthetic value 雪.")
    )
    service = ConsolidationService(store.engine)
    preview = service.preview(actor, pair[0].id, pair[1].id)
    service.apply(
        actor,
        Consolidate(
            primary_id=pair[0].id,
            secondary_id=pair[1].id,
            preview_token=preview["preview_token"],
            request_id="join",
            note="Same synthetic vehicle.",
            same_item_confirmed=True,
        ),
    )
    corrected = profiles.save(
        actor,
        change(
            pair[0].id,
            value="Premium",
            text="Synthetic fuel type Premium.",
            replaces_id=first.id,
            operation_key="correct",
        ),
    )
    assert corrected.subject_id == pair[1].id
    assert any(
        fact.id == corrected.id for fact in profiles.get(actor, pair[0].id)["facts"]
    )
    raw = json.loads(RecordExport(store.engine).download(actor))
    exported = [
        row
        for rows in raw["collections"].values()
        for row in rows
        if row.get("id") == corrected.id
    ]
    assert len(exported) == 1 and exported[0]["predicate"] == first.predicate
    bundle = tmp_path / "copy.lgbackup"
    recovery = RecoveryService(
        Settings(data_dir=directory, database_url=SecretStr(database(directory)))
    )
    password = b"synthetic recovery phrase"
    recovery.create(bundle, password)
    target = tmp_path / "restored"
    url = database(target / "data", empty=True)
    recovery.restore(bundle, target, password, url)
    restored = AuthStore(url)
    assert any(
        fact.model_dump() == corrected.model_dump()
        for fact in ProfileService(restored.engine).get(actor, pair[0].id)["facts"]
    )


def test_custom_http_writes_require_owner_session_csrf_and_original_evidence() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login(
            "alice", "alice@example.test", "Synthetic A", now=2000000000
        )
        bob = store.login("bob", "bob@example.test", "Synthetic B", now=2000000000)
        car = ProfileService(store.engine).create(
            alice.user,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="Synthetic car.",
                operation_key="car",
            ),
        )
        payload = change(
            car.id,
            custom_name="Tire size",
            value="205/55R16",
            text="Synthetic tire label 205/55R16.",
        ).model_dump(mode="json")
        client.cookies.set("lifegather_session", alice.token)
        assert client.post("/api/profiles/facts", json=payload).status_code == 403
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        saved = client.post("/api/profiles/facts", json=payload, headers=headers)
        assert saved.status_code == 200
        assert saved.json()["predicate"] == "profile_custom_tire_size"
        assert (
            client.post("/api/profiles/facts", json=payload, headers=headers).json()[
                "id"
            ]
            == saved.json()["id"]
        )
        assert (
            client.post(
                "/api/profiles/facts",
                json={**payload, "text": "No exact value.", "operation_key": "invalid"},
                headers=headers,
            ).status_code
            == 422
        )
        client.cookies.set("lifegather_session", bob.token)
        bob_headers = {
            **headers,
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        denied = client.get(f"/api/profiles/{car.id}")
        assert denied.status_code == 400
        assert "Synthetic car" not in denied.text
        assert (
            client.post(
                "/api/profiles/facts", json=payload, headers=bob_headers
            ).status_code
            == 400
        )
        assert (
            json.loads(RecordExport(store.engine).download(bob.user))["total_records"]
            == 0
        )
