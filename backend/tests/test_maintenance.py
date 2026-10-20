from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account, AuthStore
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.maintenance.schemas import (
    MaintenanceChange,
    MaintenanceCreate,
    MaintenanceHistory,
    MaintenancePage,
)
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.models import Audit, Episode
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.profiles.service import ProfileCreate, ProfileService


def prepared(tmp_path: Path) -> tuple[AuthStore, Account, Account, str]:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    alice = store.login("alice", "alice@example.test", "Alice", now=1).user
    bob = store.login("bob", "bob@example.test", "Bob", now=1).user
    vehicle = ProfileService(store.engine).create(
        alice,
        ProfileCreate(
            name="Synthetic vehicle",
            kind="vehicle",
            text="My explicitly separate synthetic vehicle.",
            operation_key="vehicle",
        ),
    )
    return store, alice, bob, vehicle.id


def plan(entity: str, **changes: Any) -> MaintenanceCreate:
    return MaintenanceCreate.model_validate(
        {
            "entity_id": entity,
            "title": "Replace cabin filter",
            "due_on": "2026-10-18",
            "timezone": "America/Los_Angeles",
            "state": "open",
            "completed_on": None,
            "text": "I chose this task and date myself; no interval is inferred.",
            "request_id": "create-task",
            **changes,
        }
    )


def change(task: dict[str, Any], request: str, **changes: Any) -> MaintenanceChange:
    return MaintenanceChange.model_validate(
        {
            "task_id": task["id"],
            "state_token": task["state_token"],
            **{
                key: task["revision"][key]
                for key in ("title", "due_on", "timezone", "state", "completed_on")
            },
            "text": "Explicit synthetic correction statement.",
            "request_id": request,
            **changes,
        }
    )


def test_private_task_dates_revisions_replay_and_stale_edits(tmp_path: Path) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    clock = int(datetime(2026, 10, 19, 0, 30, tzinfo=UTC).timestamp()) * 1_000_000
    service = MaintenanceService(store.engine, clock=lambda: clock)
    created = service.create(alice, plan(vehicle))
    assert service.create(alice, plan(vehicle)) == created
    task = service.get(alice, created["id"])
    assert task["entity_id"] == vehicle and task["target"]["id"] == vehicle
    assert task["revision"]["due_on"] == "2026-10-18"
    assert task["due_status"] == "today"  # It is still October18 in this zone.
    assert task["revision"]["state"] == "open"
    assert service.list(bob, MaintenancePage())["items"] == []
    with pytest.raises(MemoryError):
        service.get(bob, created["id"])
    with pytest.raises(MemoryError):
        service.create(bob, plan(vehicle))
    with pytest.raises(MemoryError):
        service.create(alice, plan(vehicle, title="Changed request"))
    change = MaintenanceChange(
        task_id=created["id"],
        state_token=task["state_token"],
        title="Replace cabin filter",
        due_on=date(2026, 10, 18),
        timezone="America/Los_Angeles",
        state="completed",
        completed_on=None,
        text="I completed the task. The actual completion date is unknown.",
        request_id="complete-task",
    )
    completed = service.revise(alice, change)
    assert service.revise(alice, change) == completed
    current = service.get(alice, created["id"])
    assert current["revision"]["state"] == "completed"
    assert current["revision"]["completed_on"] is None
    assert current["due_status"] == "completed"
    assert service.list(alice, MaintenancePage())["items"] == []
    with pytest.raises(MemoryError, match="changed"):
        service.revise(alice, change.model_copy(update={"request_id": "stale"}))
    reopened = change.model_copy(
        update={
            "state_token": current["state_token"],
            "state": "open",
            "due_on": None,
            "text": "I entered completion by mistake and reopened this task.",
            "request_id": "reopen-task",
        }
    )
    service.revise(alice, reopened)
    assert service.revise(alice, change) == completed  # No historical rewind.
    assert service.get(alice, created["id"])["due_status"] == "unscheduled"
    history = service.history(alice, MaintenanceHistory(task_id=created["id"]))
    assert [row["state"] for row in history["items"]] == ["open", "completed", "open"]
    assert [row["previous_id"] for row in history["items"]] == [
        None,
        created["revision_id"],
        completed["revision_id"],
    ]
    with Session(store.engine) as db:
        original = db.scalar(
            select(Episode).where(Episode.id == task["revision"]["source_id"])
        )
        assert original and plan(vehicle).text in original.text
        assert '"title": "Replace cabin filter"' in original.text
        assert "Synthetic vehicle" in original.text
        assert "request_id" not in original.text and "state_token" not in original.text
        assert original.event_date is None  # Planned due date is not an event date.
    store.engine.dispose()


@pytest.mark.parametrize(
    "due", [True, 0, 1792450000, "2026-02-30", "2026-1-02", "2026-01-02T00:00:00Z"]
)
def test_task_dates_reject_timestamp_coercion_and_invalid_calendar_dates(
    due: Any,
) -> None:
    with pytest.raises(ValidationError):
        plan("synthetic", due_on=due)


def test_dated_and_unknown_keyset_pages_are_private_filter_bound_and_stale_safe(
    tmp_path: Path,
) -> None:
    store, alice, bob, vehicle = prepared(tmp_path)
    service = MaintenanceService(store.engine)
    created = []
    for index, due in enumerate((None, "2026-10-20", "2026-10-18", None, "2026-10-18")):
        created.append(
            service.create(
                alice, plan(vehicle, due_on=due, request_id=f"task-{index}")
            )["id"]
        )
    page = service.list(alice, MaintenancePage(entity_id=vehicle, limit=2))
    rows = [*page["items"]]
    first_cursor = page["next_cursor"]
    assert first_cursor
    while page["next_cursor"]:
        page = service.list(
            alice,
            MaintenancePage(entity_id=vehicle, limit=2, cursor=page["next_cursor"]),
        )
        rows.extend(page["items"])
    assert len(rows) == 5 and {row["id"] for row in rows} == set(created)
    assert [row["revision"]["due_on"] for row in rows] == [
        "2026-10-18",
        "2026-10-18",
        "2026-10-20",
        None,
        None,
    ]
    assert rows[0]["id"] < rows[1]["id"]
    with pytest.raises(MemoryError):
        service.list(bob, MaintenancePage(cursor=first_cursor))
    with pytest.raises(MemoryError):
        service.list(alice, MaintenancePage(cursor=first_cursor))
    with pytest.raises(MemoryError):
        service.list(
            alice, MaintenancePage(entity_id=vehicle, state="all", cursor=first_cursor)
        )
    with pytest.raises(MemoryError, match="cursor"):
        service.list(alice, MaintenancePage(cursor="not-valid!"))
    service.revise(alice, change(rows[1], "changed-anchor", due_on="2026-10-19"))
    with pytest.raises(MemoryError, match="changed"):
        service.list(
            alice, MaintenancePage(entity_id=vehicle, limit=2, cursor=first_cursor)
        )
    with pytest.raises(MemoryError):
        service.history(bob, MaintenanceHistory(task_id=created[0]))
    with pytest.raises(MemoryError):
        service.history(
            alice,
            MaintenanceHistory(task_id=created[0], cursor=rows[1]["revision"]["id"]),
        )
    store.engine.dispose()


def test_concurrent_retries_and_changes_keep_one_head_and_source_per_revision(
    tmp_path: Path,
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    service = MaintenanceService(store.engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(
            pool.map(lambda _: service.create(alice, plan(vehicle)), range(2))
        )
    assert created[0] == created[1]
    task = service.get(alice, created[0]["id"])
    first = change(task, "first", due_on="2026-11-01")
    second = change(task, "second", due_on=None)

    def revise(value: MaintenanceChange) -> dict[str, str] | str:
        try:
            return service.revise(alice, value)
        except MemoryError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, [first, second]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert any(isinstance(result, str) and "changed" in result for result in results)
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(MaintenanceTask)) == 1
        assert db.scalar(select(func.count()).select_from(MaintenanceRevision)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(MaintenanceRevision)
                .where(MaintenanceRevision.superseded_at.is_(None))
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Episode)
                .where(Episode.namespace == "maintenance-revisions")
            )
            == 2
        )
    store.engine.dispose()


def test_atomic_failure_and_clock_reversal_preserve_exact_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    ticks = [100]
    service = MaintenanceService(store.engine, clock=lambda: ticks[0])
    created = service.create(alice, plan(vehicle))
    task = service.get(alice, created["id"])
    original_audit = MemoryService._audit

    def fail(
        self: MemoryService,
        db: Session,
        actor: Account,
        operation: str,
        target: str,
        now: int,
    ) -> None:
        if operation == "maintenance_revised":
            raise MemoryError("Synthetic audit failure")
        original_audit(self, db, actor, operation, target, now)

    def counts() -> list[int | None]:
        with Session(store.engine) as db:
            return [
                db.scalar(select(func.count()).select_from(model))
                for model in (Episode, MaintenanceRevision, Audit)
            ]

    before = counts()
    correction = change(task, "correction", state="canceled")
    with monkeypatch.context() as patch:
        patch.setattr(MemoryService, "_audit", fail)
        with pytest.raises(MemoryError, match="audit"):
            service.revise(alice, correction)
    assert (
        counts() == before
        and service.get(alice, task["id"])["state_token"] == task["state_token"]
    )
    ticks[0] = 50
    service.revise(alice, correction)
    history = service.history(alice, MaintenanceHistory(task_id=task["id"], limit=1))
    assert history["items"][0]["recorded_at"] == 100
    assert history["items"][0]["superseded_at"] == 101
    assert history["next_cursor"]
    later = service.history(
        alice, MaintenanceHistory(task_id=task["id"], cursor=history["next_cursor"])
    )
    assert later["items"][0]["recorded_at"] == 101
    assert later["items"][0]["state"] == "canceled"
    assert later["items"][0]["origin"]["method"] == "correction"
    assert (
        service.list(alice, MaintenancePage(state="canceled"))["items"][0]["id"]
        == task["id"]
    )
    store.engine.dispose()


@pytest.mark.parametrize(
    ("moment", "zone", "due", "expected"),
    [
        ("2026-03-08T09:59:00+00:00", "America/Los_Angeles", "2026-03-08", "today"),
        ("2026-03-08T10:01:00+00:00", "America/Los_Angeles", "2026-03-08", "today"),
        ("2026-11-01T08:59:00+00:00", "America/Los_Angeles", "2026-11-01", "today"),
        ("2026-11-01T09:01:00+00:00", "America/Los_Angeles", "2026-11-01", "today"),
        ("2026-10-19T00:30:00+00:00", "Asia/Tokyo", "2026-10-18", "overdue"),
        ("2026-10-19T00:30:00+00:00", "America/Los_Angeles", "2026-10-19", "upcoming"),
    ],
)
def test_due_status_uses_explicit_zone_through_midnight_and_dst(
    tmp_path: Path, moment: str, zone: str, due: str, expected: str
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    now = int(datetime.fromisoformat(moment).timestamp()) * 1_000_000
    service = MaintenanceService(store.engine, clock=lambda: now)
    task = service.create(alice, plan(vehicle, timezone=zone, due_on=due))
    assert service.get(alice, task["id"])["due_status"] == expected
    store.engine.dispose()
