from datetime import date

import pytest
from fastapi.testclient import TestClient

from lifegather.main import create_app
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.profiles.service import ProfileChange, ProfileCreate, ProfileService


def test_profiles_preserve_sources_history_idempotence_and_private_ownership() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000)
        service = ProfileService(store.engine)
        create = ProfileCreate(
            name="Synthetic car",
            kind="vehicle",
            text="My synthetic car",
            operation_key="create-car",
        )
        car = service.create(alice.user, create)
        assert service.create(alice.user, create).id == car.id
        change = ProfileChange(
            entity_id=car.id,
            field="model",
            value="Model A",
            text="The model is Model A",
            operation_key="model",
        )
        first = service.save(alice.user, change)
        assert service.save(alice.user, change).id == first.id
        corrected = service.save(
            alice.user,
            ProfileChange(
                entity_id=car.id,
                field="model",
                value="Model B",
                text="Correction: Model B",
                replaces_id=first.id,
                operation_key="correction",
            ),
        )
        assert corrected.replaces_id == first.id
        current = service.get(alice.user, car.id)
        assert [
            f.value for f in current["facts"] if f.predicate == "profile_model"
        ] == ["Model B"]
        history = service.get(alice.user, car.id, history=True)
        assert first.id in {f.id for f in history["facts"]}
        memory = MemoryService(store.engine)
        assert (
            memory.get_source(alice.user, str(first.evidence[0]["source_id"])).text
            == change.text
        )
        with pytest.raises(MemoryError):
            service.save(bob.user, change)
        with pytest.raises(MemoryError):
            service.get(bob.user, car.id)
        with pytest.raises(ValueError):
            service.save(
                alice.user,
                change.model_copy(
                    update={"value": "Unsupported", "operation_key": "bad"}
                ),
            )
        client.cookies.set("lifegather_session", alice.token)
        assert client.get(f"/api/profiles/{car.id}").status_code == 200
        assert (
            client.post(
                "/api/profiles/facts", json=change.model_dump(mode="json")
            ).status_code
            == 403
        )
        response = client.post(
            "/api/profiles/facts",
            json=change.model_dump(mode="json"),
            headers={
                "Origin": "http://127.0.0.1:8787",
                "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
            },
        )
        assert response.status_code == 200


def test_home_unknowns_dates_and_failed_writes_are_atomic() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("owner", "owner@example.test", "Owner", now=2000000000).user
        service = ProfileService(store.engine)
        home = service.create(
            actor,
            ProfileCreate(
                name="Synthetic home",
                kind="home",
                text="A home record for a synthetic test",
                operation_key="home",
            ),
        )
        assert home.kind == "place"
        unknown = service.save(
            actor,
            ProfileChange(
                entity_id=home.id,
                field="filter_dimensions",
                value=None,
                status="unknown",
                text="Filter size is unknown",
                operation_key="unknown",
            ),
        )
        assert unknown.value is None and unknown.status == "unknown"
        before = len(service.get(actor, home.id, history=True)["facts"])
        with pytest.raises(MemoryError):
            service.save(
                actor,
                ProfileChange(
                    entity_id=home.id,
                    field="paint",
                    value="Sage",
                    text="Paint: Sage",
                    replaces_id=unknown.id,
                    operation_key="wrong-predicate",
                ),
            )
        assert len(service.get(actor, home.id, history=True)["facts"]) == before
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProfileChange(
                entity_id=home.id,
                field="paint",
                value="Sage",
                text="Sage",
                valid_from=date(2026, 10, 18),
                valid_to=date(2026, 10, 17),
                operation_key="dates",
            )
        with pytest.raises(ValidationError):
            ProfileCreate(name=" ", kind="home", text=" ", operation_key="blank")
