import pytest
from fastapi.testclient import TestClient

from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_graph_returns_owned_sourced_relationships_and_literal_facts() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/graph/entities").status_code == 401
        store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000)
        memory = MemoryService(store.engine)
        source = memory.ingest(
            alice.user, SourceInput(text="Car is stored in Garage. Model A.")
        )
        car = memory.create_entity(
            alice.user,
            EntityInput(
                name="Car", kind="asset", source_id=source.id, operation_key="car"
            ),
        )
        garage = memory.create_entity(
            alice.user,
            EntityInput(
                name="Garage", kind="place", source_id=source.id, operation_key="garage"
            ),
        )
        relation = memory.assert_fact(
            alice.user,
            FactInput(
                subject_id=car.id,
                predicate="stored_in",
                object_id=garage.id,
                source_id=source.id,
                quote="Car is stored in Garage.",
                status="inferred",
                operation_key="location",
            ),
        )
        memory.assert_fact(
            alice.user,
            FactInput(
                subject_id=car.id,
                predicate="model",
                value="Model A",
                source_id=source.id,
                quote="Model A",
                operation_key="model",
            ),
        )
        client.cookies.set("lifegather_session", alice.token)
        page = client.get("/api/graph/entities?limit=1").json()
        assert len(page["items"]) == 1 and page["next_cursor"]
        graph = client.get("/api/graph/" + car.id).json()
        assert {node["id"] for node in graph["nodes"]} == {car.id, garage.id}
        assert graph["entity"]["id"] == car.id
        assert graph["edges"][0]["status"] == "inferred"
        assert graph["edges"][0]["evidence"][0]["source_id"] == source.id
        assert {fact["predicate"] for fact in graph["facts"]} == {"stored_in", "model"}
        assert client.get("/api/graph/" + car.id + "?depth=3").status_code == 422
        client.cookies.set("lifegather_session", bob.token)
        assert client.get("/api/graph/entities").json()["items"] == []
        assert client.get("/api/graph/" + car.id).status_code == 404
        client.cookies.set("lifegather_session", alice.token)
        memory.correct_fact(
            alice.user,
            relation.id,
            FactInput(
                subject_id=car.id,
                predicate="stored_in",
                object_id=garage.id,
                source_id=source.id,
                quote="Car is stored in Garage.",
                status="stated",
                operation_key="correct-location",
            ),
        )
        assert relation.id not in {
            edge["id"] for edge in client.get("/api/graph/" + car.id).json()["edges"]
        }
