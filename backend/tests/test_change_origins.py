import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_mcp_http import rpc, signed_headers
from test_reconciliation import setup

from lifegather.main import create_app
from lifegather.memory.history import FieldHistory, FieldHistoryRead, event_origin
from lifegather.memory.models import Audit
from lifegather.memory.origins import ChangeOrigin, change_origin
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError
from lifegather.profiles.service import ProfileCreate, ProfileService


def test_field_history_keeps_source_origin_and_replacement_separate(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    with change_origin(
        interface="web", initiator="account_request", method="manual_entry"
    ):
        source = memory.ingest(actor, SourceInput(text="Blue truck"))
        entity = memory.create_entity(
            actor,
            EntityInput(
                name="Truck", kind="asset", source_id=source.id, operation_key="truck"
            ),
        )
        first = memory.assert_fact(
            actor,
            FactInput(
                subject_id=entity.id,
                predicate="paint",
                value="Blue",
                source_id=source.id,
                quote="Blue",
                operation_key="paint-first",
            ),
        )
    with change_origin(
        interface="worker",
        initiator="scheduled",
        method="ai_inference",
        provider="openai",
        model="synthetic-model",
        related_id=entity.id,
    ):
        revised = memory.ingest(
            actor, SourceInput(text="Red paint receipt", source_type="receipt")
        )
        data = FactInput(
            subject_id=entity.id,
            predicate="paint",
            value="Red",
            status="inferred",
            source_id=revised.id,
            quote="Red",
            operation_key="paint-revised",
        )
        second = memory.correct_fact(actor, first.id, data)
    # An exact retry through another interface must not relabel the original event.
    with change_origin(interface="web", method="manual_entry"):
        assert memory.correct_fact(actor, first.id, data).id == second.id
    history = FieldHistory(auth.engine)
    page = history.get(
        actor, FieldHistoryRead(entity_id=entity.id, field="paint", limit=1)
    )
    assert page["items"][0]["origin"]["method"] == "manual_entry"
    next_page = history.get(
        actor,
        FieldHistoryRead(
            entity_id=entity.id, field="paint", cursor=page["next_cursor"]
        ),
    )
    item = next_page["items"][0]
    assert item["value"] == "Red" and item["previous"]["value"] == "Blue"
    assert (
        item["origin"]["initiator"] == "scheduled"
        and item["origin"]["model"] == "synthetic-model"
    )
    assert item["status"] == "inferred"
    sources = {e["source_id"]: e for e in item["evidence"]}
    assert sources[source.id]["source_origin"]["method"] == "manual_entry"
    assert sources[revised.id]["source_origin"]["method"] == "ai_inference"
    assert {e["source_type"] for e in item["evidence"]} == {"manual", "receipt"}
    with pytest.raises(MemoryError):
        history.get(bob, FieldHistoryRead(entity_id=entity.id, field="paint"))
    with pytest.raises(MemoryError):
        history.get(
            actor, FieldHistoryRead(entity_id=entity.id, field="owned", cursor=first.id)
        )
    auth.engine.dispose()


def test_http_and_mcp_history_owner_boundaries_and_server_owned_origin() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert (
            client.get("/api/history/fields?entity_id=x&field=paint").status_code == 401
        )
        headers, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        car = ProfileService(app.state.auth_store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic car",
                kind="vehicle",
                text="Synthetic car",
                operation_key="car",
            ),
        )
        payload = dict(
            entity_id=car.id,
            field="paint",
            value="Blue",
            text="Blue",
            operation_key="blue",
        )
        forged = {**payload, "origin": {"method": "ai_inference"}}
        assert (
            client.post("/api/profiles/facts", headers=headers, json=forged).status_code
            == 422
        )
        saved = client.post(
            "/api/profiles/facts",
            headers={**headers, "x-change-origin": "ai_inference"},
            json=payload,
        )
        assert saved.status_code == 200
        path = f"/api/history/fields?entity_id={car.id}&field=profile_paint"
        response = client.get(path, headers=headers)
        assert response.headers["cache-control"] == "no-store"
        row = response.json()["items"][0]
        assert row["origin"]["method"] == "manual_entry"
        assert row["origin"]["interface"] == "web"
        assert row["status"] == "stated"
        assert client.get(path, headers=bob).status_code == 400
        args = dict(entity_id=car.id, field="profile_paint")
        assert (
            not rpc(client, headers, "memory_field_history", args)
            .json()["result"]
            .get("isError")
        )
        denied = rpc(client, bob, "memory_field_history", args).json()
        assert denied["result"]["isError"] and "Blue" not in str(denied)
        assert (
            rpc(
                client, headers, "memory_field_history", {**args, "user_id": actor.id}
            ).status_code
            == 400
        )
        assert client.get(path + "&limit=11", headers=headers).status_code == 422
        external = rpc(
            client,
            headers,
            "memory_save_text",
            {"text": "External client statement", "request_id": "external-save"},
        )
        assert not external.json()["result"].get("isError")
        with Session(app.state.auth_store.engine) as db:
            event = db.scalar(
                select(Audit)
                .where(Audit.operation == "source_ingested")
                .order_by(Audit.recorded_at.desc())
            )
            assert event is not None
            origin = event_origin(db, actor, event.target_id, ("source_ingested",))
            assert origin is not None
            assert (
                origin["interface"] == "mcp"
                and origin["initiator"] == "external_client"
            )


def test_origins_do_not_guess_legacy_or_claim_independent_verification(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    source = memory.ingest(actor, SourceInput(text="Unknown maker"))
    entity = memory.create_entity(
        actor,
        EntityInput(
            name="Item", kind="asset", source_id=source.id, operation_key="item"
        ),
    )
    fact = memory.assert_fact(
        actor,
        FactInput(
            subject_id=entity.id,
            predicate="maker",
            value="Unknown",
            source_id=source.id,
            operation_key="maker",
        ),
    )
    with Session(auth.engine) as db, db.begin():
        event = db.scalar(select(Audit).where(Audit.target_id == fact.id))
        assert event is not None
        event.provenance_json = None
    item = FieldHistory(auth.engine).get(
        actor, FieldHistoryRead(entity_id=entity.id, field="maker")
    )["items"][0]
    assert item["origin"] is None and item["status"] == "stated"
    assert ChangeOrigin().initiator == "unknown"
    auth.engine.dispose()


def test_origin_context_resets_across_async_tasks_and_failed_transactions(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)

    async def create(method: str) -> None:
        with change_origin(method=method):
            await asyncio.sleep(0)
            memory.ingest(actor, SourceInput(text=method))

    async def both() -> None:
        await asyncio.gather(create("manual_entry"), create("ai_extraction"))

    asyncio.run(both())
    memory.ingest(actor, SourceInput(text="After context"))
    with Session(auth.engine) as db:
        origins = [
            e.provenance_json
            for e in db.scalars(select(Audit).order_by(Audit.recorded_at))
        ]
        assert "manual_entry" in str(origins) and "ai_extraction" in str(origins)
        assert "unspecified" in str(origins[-1])
        before = db.scalar(select(func.count()).select_from(Audit))
    with pytest.raises(RuntimeError), change_origin(method="ai_inference"):
        with memory._write() as db:
            memory._ingest_in(db, actor, SourceInput(text="Must roll back"))
            raise RuntimeError("synthetic failure")
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count()).select_from(Audit)) == before
    auth.engine.dispose()


def test_migration_preserves_existing_memory_and_leaves_legacy_origins_unknown(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather

    auth, actor, _, memory, _ = setup(tmp_path)
    source = memory.ingest(actor, SourceInput(text="Legacy source"))
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with auth.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0021_email_discovery")
    auth.migrate()
    assert memory.get_source(actor, source.id).text == "Legacy source"
    with Session(auth.engine) as db:
        assert (
            db.scalar(select(Audit.provenance_json).where(Audit.target_id == source.id))
            is None
        )
    auth.engine.dispose()


def test_competing_statements_remain_distinct_and_large_history_requires_smaller_page(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    source = memory.ingest(actor, SourceInput(text="Synthetic evidence" * 100))
    entity = memory.create_entity(
        actor,
        EntityInput(
            name="Item", kind="asset", source_id=source.id, operation_key="entity"
        ),
    )
    for index in range(10):
        memory.assert_fact(
            actor,
            FactInput(
                subject_id=entity.id,
                predicate="paint",
                value=str(index) + "🌿" * 1999,
                source_id=source.id,
                quote=source.text,
                operation_key=str(index),
            ),
        )
    history = FieldHistory(auth.engine)
    with pytest.raises(MemoryError, match="smaller page"):
        history.get(
            actor, FieldHistoryRead(entity_id=entity.id, field="paint", limit=10)
        )
    result = history.get(
        actor, FieldHistoryRead(entity_id=entity.id, field="paint", limit=1)
    )
    assert result["next_cursor"]
    assert result["items"][0]["previous"] is None
    assert result["items"][0]["superseded_at"] is None
    auth.engine.dispose()
