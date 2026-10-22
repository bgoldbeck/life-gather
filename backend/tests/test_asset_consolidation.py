from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import database, restore_copy
from sqlalchemy.orm import Session
from stored_files import files
from test_reconciliation import discovery, setup

from lifegather.assets.consolidation import (
    Consolidate,
    ConsolidationService,
    ReverseConsolidation,
)
from lifegather.assets.identity import canonical_id, member_ids
from lifegather.assets.service import AssetList, AssetService
from lifegather.auth.store import AuthStore
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.service import ReconciliationService


def prepared(tmp_path: Path) -> tuple[Any, ...]:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    source = memory.ingest(
        actor, SourceInput(text="Synthetic first and second mower. Red. Blue.")
    )
    records = [
        memory.create_entity(
            actor,
            EntityInput(
                name=name,
                kind="asset",
                source_id=source.id,
                operation_key=name,
            ),
        )
        for name in ("first mower", "second mower")
    ]
    service = ConsolidationService(auth.engine)

    def request() -> Consolidate:
        preview = service.preview(actor, records[0].id, records[1].id)
        return Consolidate(
            primary_id=records[0].id,
            secondary_id=records[1].id,
            preview_token=preview["preview_token"],
            request_id="join",
            note="Same physical mower.",
            same_item_confirmed=True,
        )

    return auth, actor, bob, memory, source, records, service, request


def test_history_pages_reversals_and_rejects_unrelated_cursors(tmp_path: Path) -> None:
    from lifegather.assets.service import AssetRead

    auth, actor, bob, _, _, records, service, request = prepared(tmp_path)
    choices = []
    for index in range(3):
        saved = service.apply(
            actor, request().model_copy(update={"request_id": f"join-{index}"})
        )
        choices.append(saved)
        service.reverse(
            actor,
            ReverseConsolidation(
                consolidation_id=saved["id"],
                request_id=f"reverse-{index}",
                note="Separate again.",
            ),
        )
    assets = AssetService(auth.engine)
    cursor = ""
    seen = []
    for expected in reversed(choices):
        page = assets.get(
            actor, AssetRead(asset_id=records[1].id, identity_cursor=cursor, limit=1)
        )
        row = page["identity_history"][0]
        assert row["id"] == expected["id"]
        assert row["source_id"] == expected["source_id"]
        assert row["reverse_source_id"] and row["superseded_at"] > row["recorded_at"]
        seen.append(row["id"])
        cursor = page["next_identity_cursor"]
    assert len(set(seen)) == 3 and cursor is None
    with pytest.raises(MemoryError):
        assets.get(
            bob, AssetRead(asset_id=records[0].id, identity_cursor=choices[0]["id"])
        )
    with pytest.raises(MemoryError, match="cursor"):
        assets.get(
            actor, AssetRead(asset_id=records[0].id, identity_cursor="unrelated")
        )


def test_service_revalidates_copied_confirmation(tmp_path: Path) -> None:
    from pydantic import ValidationError

    auth, actor, _, _, _, _, service, request = prepared(tmp_path)
    with pytest.raises(ValidationError, match="Confirm the same physical item"):
        service.apply(
            actor, request().model_copy(update={"same_item_confirmed": False})
        )
    from sqlalchemy import select

    from lifegather.assets.models import AssetConsolidation

    with Session(auth.engine) as db:
        assert db.scalar(select(AssetConsolidation)) is None


def test_conflicts_aliases_graph_and_temporal_identity_keep_original_evidence(
    tmp_path: Path,
) -> None:
    from lifegather.chat.context import ContextRead, WorkspaceContexts
    from lifegather.memory.history import FieldHistory, FieldHistoryRead
    from lifegather.profiles.service import ProfileChange, ProfileService

    auth, actor, _, memory, source, records, service, request = prepared(tmp_path)
    profile = ProfileService(auth.engine)
    facts = [
        profile.save(
            actor,
            ProfileChange(
                entity_id=row.id,
                field="paint",
                value=color,
                text=source.text,
                operation_key=color,
            ),
        )
        for row, color in zip(records, ("Red", "Blue"), strict=True)
    ]
    memory.add_alias(actor, records[1].id, "second mower", source.id)
    old_context = WorkspaceContexts(auth.engine).read(
        actor, ContextRead(page="Assets", entity_id=records[0].id)
    )
    saved = service.apply(actor, request())
    current = memory.facts(actor, records[0].id)
    assert {fact.id for fact in current} == {fact.id for fact in facts}
    assert {fact.subject_id for fact in current} == {row.id for row in records}
    assert memory.find_entities(actor, "second mower")[0].id == records[0].id
    assert memory.get_entity(actor, records[1].id).id == records[0].id
    assert (
        memory.get_entity(actor, records[1].id, known_at=saved["recorded_at"] - 1).id
        == records[1].id
    )
    assert {
        fact.id
        for fact in memory.facts(
            actor, records[1].id, known_at=saved["recorded_at"] - 1
        )
    } == {facts[1].id}
    assert len(profile.get(actor, records[0].id)["facts"]) == 2
    assert (
        len(
            FieldHistory(auth.engine).get(
                actor, FieldHistoryRead(entity_id=records[0].id, field="profile_paint")
            )["items"]
        )
        == 2
    )
    context = WorkspaceContexts(auth.engine).read(
        actor, ContextRead(page="Assets", entity_id=records[0].id)
    )
    assert (
        context["version"] != old_context["version"]
        and context["fields"]["paint"]["count"] == 2
    )
    service.reverse(
        actor,
        ReverseConsolidation(
            consolidation_id=saved["id"], request_id="reverse", note="Separate again."
        ),
    )
    assert len(memory.facts(actor, records[1].id, known_at=saved["recorded_at"])) == 2
    assert len(memory.facts(actor, records[1].id)) == 1


def test_atomic_apply_and_reverse_roll_back_all_sources_and_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import func, select

    from lifegather.assets.models import AssetConsolidation, ConsolidationMember
    from lifegather.memory.models import Episode

    auth, actor, _, _, _, records, service, request = prepared(tmp_path)
    data = request()
    with Session(auth.engine) as db:
        before = db.scalar(select(func.count()).select_from(Episode))
    original = service.memory._audit

    def fail(db: Session, owner: Any, operation: str, target: str, now: int) -> None:
        if operation in {"asset_consolidated", "asset_consolidation_reversed"}:
            raise MemoryError("Synthetic audit failure")
        original(db, owner, operation, target, now)

    with monkeypatch.context() as patch:
        patch.setattr(service.memory, "_audit", fail)
        with pytest.raises(MemoryError, match="Synthetic"):
            service.apply(actor, data)
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count()).select_from(Episode)) == before
        assert db.scalar(select(func.count()).select_from(AssetConsolidation)) == 0
        assert db.scalar(select(func.count()).select_from(ConsolidationMember)) == 0
    saved = service.apply(actor, data)
    reverse = ReverseConsolidation(
        consolidation_id=saved["id"], request_id="reverse", note="Separate."
    )
    with monkeypatch.context() as patch:
        patch.setattr(service.memory, "_audit", fail)
        with pytest.raises(MemoryError):
            service.reverse(actor, reverse)
    with Session(auth.engine) as db:
        assert canonical_id(db, actor, records[1].id) == records[0].id
    assert service.reverse(actor, reverse)["operation"] == "reverse"


def test_conflicting_serials_and_replacement_are_refused(tmp_path: Path) -> None:
    from lifegather.assets.replacements import ReplacementRecord, ReplacementService
    from lifegather.profiles.service import ProfileChange, ProfileService

    auth, actor, _, _, _, records, service, _ = prepared(tmp_path)
    profile = ProfileService(auth.engine)
    for index, row in enumerate(records):
        serial = f"S{index}"
        profile.save(
            actor,
            ProfileChange(
                entity_id=row.id,
                field="serial",
                value=serial,
                text=serial,
                operation_key=serial,
            ),
        )
    with pytest.raises(MemoryError, match="identifiers"):
        service.preview(actor, records[0].id, records[1].id)
    auth2, owner, _, _, _, pair, service2, _ = prepared(tmp_path / "replacement")
    ReplacementService(auth2.engine).change(
        owner,
        ReplacementRecord(
            asset_id=pair[0].id,
            target_asset_id=pair[1].id,
            request_id="replacement",
            note="Second mower replaced the first.",
        ),
    )
    with pytest.raises(MemoryError, match="replacement"):
        service2.preview(owner, pair[0].id, pair[1].id)


def test_complete_bounds_and_request_conflicts_do_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic import ValidationError

    from lifegather.assets import comparison

    _, actor, _, _, _, records, service, request = prepared(tmp_path)
    data = request()
    with pytest.raises(ValidationError):
        Consolidate.model_validate({**data.model_dump(), "same_item_confirmed": False})
    with monkeypatch.context() as patch:
        patch.setattr(comparison, "MAX_BYTES", 1)
        with pytest.raises(MemoryError, match="limits"):
            service.preview(actor, records[0].id, records[1].id)
    service.apply(actor, data)
    with pytest.raises(MemoryError, match="conflict"):
        service.apply(actor, data.model_copy(update={"note": "Different explanation"}))


def test_http_mcp_private_confirmed_replay_and_export(tmp_path: Path) -> None:
    import json

    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app
    from lifegather.memory.export import RecordExport

    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(client.app, "consolidation-alice")
        bob, _ = signed_headers(client.app, "consolidation-bob")
        memory = MemoryService(app.state.auth_store.engine)
        source = memory.ingest(actor, SourceInput(text="Synthetic duplicate mower."))
        pair = [
            memory.create_entity(
                actor,
                EntityInput(
                    name=f"Mower {index}",
                    kind="asset",
                    source_id=source.id,
                    operation_key=str(index),
                ),
            )
            for index in range(2)
        ]
        body = {"primary_id": pair[0].id, "secondary_id": pair[1].id}
        assert (
            client.post("/api/assets/consolidation/preview", json=body).status_code
            == 401
        )
        assert (
            client.post(
                "/api/assets/consolidation/preview", headers=bob, json=body
            ).status_code
            == 400
        )
        preview = rpc(client, alice, "asset_consolidation_preview", body).json()[
            "result"
        ]["structuredContent"]
        data = {
            **body,
            "preview_token": preview["preview_token"],
            "request_id": "private-join",
            "same_item_confirmed": True,
            "note": "Same item.",
        }
        assert (
            client.post(
                "/api/assets/consolidation/apply",
                headers={"Cookie": alice["Cookie"]},
                json=data,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/assets/consolidation/apply",
                headers=alice,
                json={**data, "user_id": "forged"},
            ).status_code
            == 422
        )
        saved = rpc(client, alice, "asset_consolidate", data).json()["result"][
            "structuredContent"
        ]
        assert (
            client.post(
                "/api/assets/consolidation/apply", headers=alice, json=data
            ).json()
            == saved
        )
        exported = json.loads(RecordExport(memory.engine).download(actor))
        assert exported["format"] == "lifegather-records/4"
        assert exported["collections"]["asset_consolidations"][0]["id"] == saved["id"]
        assert (
            not rpc(
                client,
                bob,
                "asset_consolidation_reverse",
                {
                    "consolidation_id": saved["id"],
                    "request_id": "foreign",
                    "note": "No.",
                },
            )
            .json()["result"]
            .get("structuredContent")
        )


def test_complete_identity_current_reads_future_discovery_and_reversal(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    incoming = discovery(memory, actor)
    receipt = reconcile.discover(actor, incoming)
    original = memory.ingest(actor, SourceInput(text="Synthetic mower is red."))
    manual = memory.create_entity(
        actor,
        EntityInput(
            name="Synthetic mower",
            kind="asset",
            source_id=original.id,
            operation_key="manual",
        ),
    )
    fact = memory.assert_fact(
        actor,
        FactInput(
            subject_id=manual.id,
            predicate="color",
            value="red",
            source_id=original.id,
            quote=original.text,
            operation_key="red",
        ),
    )
    service = ConsolidationService(auth.engine)
    preview = service.preview(actor, manual.id, receipt.asset_ids[0])
    data = Consolidate(
        primary_id=manual.id,
        secondary_id=receipt.asset_ids[0],
        preview_token=preview["preview_token"],
        request_id="join",
        note="I confirm both records describe the same physical mower.",
        same_item_confirmed=True,
    )
    saved = service.apply(actor, data)
    assert service.apply(actor, data) == saved
    with Session(auth.engine) as db:
        assert canonical_id(db, actor, receipt.asset_ids[0]) == manual.id
        assert set(member_ids(db, actor, manual.id)) == {
            manual.id,
            receipt.asset_ids[0],
        }
        assert canonical_id(db, bob, receipt.asset_ids[0]) == receipt.asset_ids[0]
    assert {
        row["id"] for row in AssetService(auth.engine).list(actor, AssetList())["items"]
    } == {manual.id}
    assert any(row.id == fact.id for row in memory.facts(actor, receipt.asset_ids[0]))
    assert memory.get_source(actor, original.id).text == original.text
    reverse = ReverseConsolidation(
        consolidation_id=saved["id"],
        request_id="separate",
        note="Undo identity choice.",
    )
    restored = service.reverse(actor, reverse)
    assert service.reverse(actor, reverse) == restored
    assert service.apply(actor, data) == saved
    with Session(auth.engine) as db:
        assert canonical_id(db, actor, receipt.asset_ids[0]) == receipt.asset_ids[0]
    preview = service.preview(actor, manual.id, receipt.asset_ids[0])
    data = data.model_copy(
        update={"request_id": "join-again", "preview_token": preview["preview_token"]}
    )
    saved = service.apply(actor, data)
    later = reconcile.discover(actor, discovery(memory, actor, key="shipping"))
    assert later.asset_ids == [manual.id]
    with pytest.raises(MemoryError, match="changed"):
        service.reverse(
            actor,
            reverse.model_copy(
                update={"consolidation_id": saved["id"], "request_id": "later"}
            ),
        )
    snapshot = tmp_path / "consolidated.jsonl"
    operator_snapshot(auth.engine, snapshot)
    recovered = AuthStore(restore_copy(snapshot))
    recovered.migrate()
    assert any(
        row.id == fact.id
        for row in MemoryService(recovered.engine).facts(actor, manual.id)
    )
    assert ReconciliationService(recovered.engine).discover(
        actor, incoming
    ).asset_ids == [manual.id]


def test_owner_staleness_overlap_concurrency_and_distinct_units(tmp_path: Path) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    first = reconcile.discover(actor, discovery(memory, actor))
    other = reconcile.discover(actor, discovery(memory, actor, key="two", order="A101"))
    service = ConsolidationService(auth.engine)
    with pytest.raises(MemoryError):
        service.preview(bob, first.asset_ids[0], other.asset_ids[0])
    preview = service.preview(actor, first.asset_ids[0], other.asset_ids[0])
    data = Consolidate(
        primary_id=first.asset_ids[0],
        secondary_id=other.asset_ids[0],
        preview_token=preview["preview_token"],
        request_id="join",
        note="Same item.",
        same_item_confirmed=True,
    )
    source = memory.ingest(actor, SourceInput(text="Synthetic detail"))
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=first.asset_ids[0],
            predicate="detail",
            value="Synthetic detail",
            source_id=source.id,
            quote=source.text,
            operation_key="detail",
        ),
    )
    with pytest.raises(MemoryError, match="changed"):
        service.apply(actor, data)
    fresh = service.preview(actor, first.asset_ids[0], other.asset_ids[0])
    data = data.model_copy(update={"preview_token": fresh["preview_token"]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.apply(actor, data), range(2)))
    assert results[0] == results[1]
    with pytest.raises(MemoryError):
        service.preview(actor, first.asset_ids[0], other.asset_ids[0])
    two = reconcile.discover(
        actor, discovery(memory, actor, key="pair", order="A102", quantity=2)
    )
    with pytest.raises(MemoryError, match="units"):
        service.preview(actor, *two.asset_ids)


def test_galleries_graph_and_profile_corrections_use_one_current_identity(
    tmp_path: Path,
) -> None:
    from test_photos import image_bytes

    from lifegather.assets.service import AssetRead
    from lifegather.chat.recall import RecallPlan, RecallTools
    from lifegather.chat.service import ChatService
    from lifegather.photos.service import PhotoDetach, PhotoList, PhotoService
    from lifegather.profiles.service import ProfileChange, ProfileService

    auth, actor, _, memory, source, records, service, request = prepared(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "synthetic.jpg", asset_id=records[1].id)
    place = memory.create_entity(
        actor,
        EntityInput(
            name="Synthetic garage",
            kind="place",
            source_id=source.id,
            operation_key="garage",
        ),
    )
    relation = memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[1].id,
            predicate="stored_in",
            object_id=place.id,
            source_id=source.id,
            quote=source.text,
            operation_key="garage-relation",
        ),
    )
    profiles = ProfileService(auth.engine)
    old = profiles.save(
        actor,
        ProfileChange(
            entity_id=records[1].id,
            field="paint",
            value="Red",
            text=source.text,
            operation_key="paint",
        ),
    )
    saved = service.apply(actor, request())
    assert (
        photos.list(actor, PhotoList(asset_id=records[0].id))["items"][0]["id"]
        == photo["id"]
    )
    graph = memory.related(actor, place.id)
    assert {row.id for row in graph["nodes"]} == {place.id, records[0].id}
    assert (
        next(edge for edge in graph["edges"] if edge.id == relation.id).subject_id
        == records[0].id
    )
    assert graph["identity_projection"] == [
        {"original_id": records[1].id, "primary_id": records[0].id}
    ]
    detail = AssetService(auth.engine).get(actor, AssetRead(asset_id=records[1].id))
    assert detail["asset"]["id"] == records[0].id
    assert detail["consolidation"]["id"] == saved["id"]
    recall = RecallTools(ChatService(auth.engine)).collect(
        actor,
        RecallPlan(
            query="mower", entity_names=["second mower"], include_connections=True
        ),
    )
    assert len(recall["records"]) == 1
    assert recall["records"][0]["consolidation"]["secondary_id"] == records[1].id
    corrected = profiles.save(
        actor,
        ProfileChange(
            entity_id=records[0].id,
            field="paint",
            value="Blue",
            text=source.text,
            operation_key="correct-paint",
            replaces_id=old.id,
        ),
    )
    assert corrected.subject_id == records[1].id and corrected.replaces_id == old.id
    assert profiles.get(actor, records[0].id)["facts"][0].value == "Blue"
    photos.detach(
        actor,
        PhotoDetach(
            photo_id=photo["id"],
            asset_id=records[0].id,
            expected_updated_at=photo["updated_at"],
        ),
    )
    assert photos.list(actor, PhotoList(asset_id=records[0].id))["items"] == []
    with pytest.raises(MemoryError, match="changed"):
        service.reverse(
            actor,
            ReverseConsolidation(
                consolidation_id=saved["id"], request_id="reverse", note="Separate."
            ),
        )


def test_identity_history_is_monotonic_and_old_previews_cannot_cross_reversal(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _, records, service, request = prepared(tmp_path)
    data = request()
    saved = service.apply(actor, data)
    service.memory.clock = lambda: 1
    reversed_result = service.reverse(
        actor,
        ReverseConsolidation(
            consolidation_id=saved["id"], request_id="reverse", note="Separate."
        ),
    )
    with pytest.raises(MemoryError, match="changed"):
        service.apply(actor, data.model_copy(update={"request_id": "old-preview"}))
    next_result = service.apply(
        actor, request().model_copy(update={"request_id": "fresh"})
    )
    assert (
        next_result["recorded_at"]
        > reversed_result["recorded_at"]
        > saved["recorded_at"]
    )
    with Session(auth.engine) as db:
        assert member_ids(
            db, actor, records[0].id, known_at=reversed_result["recorded_at"]
        ) == [records[0].id]


def test_explicit_group_ownership_advances_both_original_action_histories(
    tmp_path: Path,
) -> None:
    from lifegather.assets.actions import ActionService, AssetChange
    from lifegather.assets.service import AssetRead

    auth, actor, _, memory, _, records, service, request = prepared(tmp_path)
    actions = ActionService(auth.engine)
    actions.apply(
        actor,
        AssetChange(
            asset_id=records[1].id,
            operation="ownership",
            status="sold",
            request_id="sale",
            note="Sold this mower.",
        ),
    )
    choice = service.apply(actor, request())
    actions.memory.clock = lambda: 1
    owned = actions.apply(
        actor,
        AssetChange(
            asset_id=records[0].id,
            operation="ownership",
            status="owned",
            request_id="own",
            note="I own this mower again.",
        ),
    )
    assert AssetService(auth.engine).get(actor, AssetRead(asset_id=records[0].id))[
        "in_inventory"
    ]
    assert owned["original_record_status_fact_ids"]
    statements = [
        fact
        for fact in memory.facts(actor, records[0].id)
        if fact.predicate == "owned" and fact.superseded_at is None
    ]
    assert all(fact.value is True for fact in statements)
    assert all(fact.recorded_at > choice["recorded_at"] for fact in statements)
    actions.apply(
        actor,
        AssetChange(
            asset_id=records[0].id,
            operation="ownership",
            status="sold",
            expected_action_id=owned["id"],
            request_id="sold-again",
            note="Sold it again.",
        ),
    )
    assert not AssetService(auth.engine).get(actor, AssetRead(asset_id=records[0].id))[
        "in_inventory"
    ]


def test_upgrade_preserves_originals_and_database_blocks_foreign_members(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import insert, text
    from sqlalchemy.exc import IntegrityError

    import lifegather
    from lifegather.assets.models import ConsolidationMember

    store = AuthStore(database(tmp_path / "old", empty=True))
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0022_change_origins")
    actor = store.login("old", "old@example.test", "Old", now=1).user
    memory = MemoryService(store.engine)
    source = memory.ingest(actor, SourceInput(text="Preserved synthetic evidence."))
    records = [
        memory.create_entity(
            actor,
            EntityInput(
                name=name, kind="asset", source_id=source.id, operation_key=name
            ),
        )
        for name in ("first", "second")
    ]
    store.migrate()
    assert memory.get_source(actor, source.id).text == source.text
    service = ConsolidationService(store.engine)
    preview = service.preview(actor, records[0].id, records[1].id)
    saved = service.apply(
        actor,
        Consolidate(
            primary_id=records[0].id,
            secondary_id=records[1].id,
            preview_token=preview["preview_token"],
            request_id="join",
            note="Same item.",
            same_item_confirmed=True,
        ),
    )
    bob = store.login("other", "other@example.test", "Other", now=1).user
    with pytest.raises(IntegrityError), store.engine.begin() as connection:
        connection.execute(
            insert(ConsolidationMember).values(
                user_id=bob.id, entity_id=records[0].id, consolidation_id=saved["id"]
            )
        )
    with store.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0033_account_row_security"
        )
