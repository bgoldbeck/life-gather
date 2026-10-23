import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from database_support import restore_copy
from pydantic import ValidationError
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from stored_files import files
from test_maintenance import change, plan, prepared

from lifegather.auth.store import AuthStore
from lifegather.chat.privacy import ConversationDelete, ConversationPrivacy
from lifegather.chat.service import ChatService, TurnInput
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.maintenance.schemas import MaintenanceHistory, MaintenancePage
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.export import RecordExport
from lifegather.memory.models import Episode
from lifegather.profiles.service import ProfileCreate, ProfileService


def test_personal_json_zip_and_snapshot_keep_only_own_exact_task_history(
    tmp_path: Path,
) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    service = MaintenanceService(store.engine)
    original_text = (
        'Synthetic original statement: 日本語, "quotes".\nNo inferred interval.'
    )
    created = service.create(
        alice, plan(vehicle, text=original_text, due_on="2028-02-29")
    )
    first = service.get(alice, created["id"])
    service.revise(
        alice,
        change(
            first,
            "completion",
            state="completed",
            completed_on="2028-02-28",
            text="Completed on my explicitly stated 2028-02-28.",
        ),
    )
    other = ProfileService(store.engine).create(
        bob,
        ProfileCreate(
            name="Private other vehicle",
            kind="vehicle",
            text="Other owner's source.",
            operation_key="other",
        ),
    )
    foreign = service.create(
        bob, plan(other.id, title="PRIVATE OTHER TASK", request_id="other-task")
    )
    current = service.get(alice, created["id"])
    chat = ChatService(store.engine)
    transcript = chat.create(alice)["id"]
    turn, _ = chat.begin(
        alice,
        transcript,
        TurnInput(
            request_id="ephemeral",
            mode="search",
            text="Remove this synthetic transcript",
        ),
    )
    chat.finish(alice, turn["id"], {"text": "Synthetic ephemeral reply"})
    privacy = ConversationPrivacy(store.engine)
    privacy.delete(
        alice,
        transcript,
        ConversationDelete(
            preview_token=privacy.preview(alice, transcript)["preview_token"],
            confirmed=True,
        ),
    )
    assert service.get(alice, created["id"])["revision"] == current["revision"]
    raw = RecordExport(store.engine).download(alice)
    exported = json.loads(raw)
    assert exported["format"] == "lifegather-records/6"
    assert b"Remove this synthetic transcript" not in raw
    collections = exported["collections"]
    assert len(collections["maintenance_tasks"]) == 1
    assert collections["chat_conversations"] == [] and collections["chat_turns"] == []
    assert collections["maintenance_tasks"][0]["entity_id"] == vehicle
    revisions = sorted(
        collections["maintenance_revisions"], key=lambda row: row["recorded_at"]
    )
    assert [row["state"] for row in revisions] == ["open", "completed"]
    assert [row["due_on"] for row in revisions] == ["2028-02-29"] * 2
    assert [row["completed_on"] for row in revisions] == [None, "2028-02-28"]
    sources = {row["id"]: row for row in collections["memory_sources"]}
    assert sources[first["revision"]["source_id"]]["text"].endswith(original_text)
    assert sources[first["revision"]["source_id"]]["event_date"] is None
    assert b"PRIVATE OTHER TASK" not in raw and foreign["id"].encode() not in raw
    assert all("user_id" not in row for rows in collections.values() for row in rows)
    with ZipFile(
        BytesIO(PersonalArchive(store.engine, files(store.engine)).download(alice))
    ) as archive:
        records = archive.read("records.json")
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["records_format"] == "lifegather-records/6"
        assert manifest["records"]["sha256"] == hashlib.sha256(records).hexdigest()
        assert json.loads(records)["collections"] == collections
    copied = tmp_path / "copied.jsonl"
    operator_snapshot(store.engine, copied)
    recovered = AuthStore(restore_copy(copied))
    recovered_service = MaintenanceService(recovered.engine)
    assert (
        recovered_service.get(alice, created["id"])["revision"] == current["revision"]
    )
    assert recovered_service.history(
        alice, MaintenanceHistory(task_id=created["id"])
    ) == service.history(alice, MaintenanceHistory(task_id=created["id"]))
    assert (
        recovered_service.list(bob, MaintenancePage())["items"][0]["id"]
        == foreign["id"]
    )
    recovered.engine.dispose()
    store.engine.dispose()


def test_migration_upgrade_and_downgrade_leave_existing_sources_and_identity_intact(
    tmp_path: Path,
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    with Session(store.engine) as db:
        legacy = [(row.id, row.text) for row in db.scalars(select(Episode))]
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/lifegather/migrations")
    )

    def downgrade() -> None:
        with store.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0023_asset_consolidation")

    downgrade()
    with store.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0023_asset_consolidation"
        )
    store.migrate()
    service = MaintenanceService(store.engine)
    created = service.create(alice, plan(vehicle))
    service.revise(
        alice,
        change(
            service.get(alice, created["id"]),
            "complete",
            state="completed",
            completed_on="2026-10-19",
        ),
    )
    downgrade()
    with store.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0023_asset_consolidation"
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM memory_entities WHERE id=:id"),
                {"id": vehicle},
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name='maintenance_tasks'"
                )
            )
            == 0
        )
    store.migrate()
    with Session(store.engine) as db:
        assert {(row.id, row.text) for row in db.scalars(select(Episode))}.issuperset(
            legacy
        )
    assert service.list(alice, MaintenancePage())["items"] == []
    store.engine.dispose()


def test_database_constraints_enforce_owners_task_chain_and_one_current_head(
    tmp_path: Path,
) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    service = MaintenanceService(store.engine)
    first = service.create(alice, plan(vehicle))
    second = service.create(alice, plan(vehicle, request_id="second"))
    with Session(store.engine) as db:
        row = db.scalar(
            select(MaintenanceRevision).where(
                MaintenanceRevision.id == first["revision_id"]
            )
        )
        assert row
        fields: dict[str, Any] = {
            column.key: getattr(row, column.key)
            for column in MaintenanceRevision.__table__.columns
        }
        foreign_source = Episode(
            id=str(uuid4()),
            user_id=bob.id,
            source_key="synthetic-other",
            text="Synthetic foreign source",
            source_type="manual",
            namespace="synthetic",
            external_id=None,
            content_hash="a" * 64,
            event_date=None,
            recorded_at=1,
        )
        db.add(foreign_source)
        db.commit()
        source_id = foreign_source.id
    cases = [
        (
            {
                "user_id": bob.id,
                "source_id": source_id,
                "superseded_at": fields["recorded_at"] + 1,
            },
            "foreign key",
        ),
        (
            {
                "previous_id": second["revision_id"],
                "superseded_at": fields["recorded_at"] + 1,
            },
            "foreign key",
        ),
        ({}, "unique"),
        (
            {
                "state": "open",
                "completed_on": date(2026, 10, 19),
                "superseded_at": fields["recorded_at"] + 1,
            },
            "check",
        ),
    ]
    for changes, expected in cases:
        with (
            pytest.raises(IntegrityError, match=expected),
            store.engine.begin() as connection,
        ):
            connection.execute(
                insert(MaintenanceRevision).values(
                    {
                        **fields,
                        "id": str(uuid4()),
                        "request_id": str(uuid4()),
                        **changes,
                    }
                )
            )
    with (
        pytest.raises(IntegrityError, match="foreign key"),
        store.engine.begin() as connection,
    ):
        connection.execute(
            insert(MaintenanceTask).values(
                id=str(uuid4()),
                user_id=bob.id,
                entity_id=vehicle,
                source_id=source_id,
                request_id="foreign",
                fingerprint="a" * 64,
                recorded_at=1,
            )
        )
    with pytest.raises(ValidationError):
        service.create(alice, plan(vehicle).model_copy(update={"due_on": True}))
    with pytest.raises(ValidationError):
        plan(vehicle, timezone="../../private")
    with pytest.raises(ValidationError):
        plan(vehicle, state="open", completed_on="2026-10-19")
    with pytest.raises(ValidationError):
        plan(vehicle, user_id=alice.id)
    store.engine.dispose()
