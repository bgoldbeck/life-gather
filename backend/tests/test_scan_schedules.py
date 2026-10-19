import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_reconciliation import setup
from test_scans import registry

from lifegather.memory.service import MemoryError
from lifegather.scans.recurrence import next_occurrence
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker


def instant(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp())


@pytest.mark.parametrize(
    ("after", "time", "expected"),
    [
        ("2025-03-09T08:00:00", "02:30", "2025-03-09T10:00:00"),
        ("2025-11-02T07:00:00", "01:30", "2025-11-02T08:30:00"),
        ("2025-11-02T08:30:00", "01:30", "2025-11-03T09:30:00"),
    ],
)
def test_recurrence_handles_missing_and_repeated_wall_times(
    after: str, time: str, expected: str
) -> None:
    assert next_occurrence(
        instant(after), "America/Los_Angeles", "daily", 0, time
    ) == instant(expected)


def test_modular_dispatch_catchup_overlap_owner_edit_pause(tmp_path: Path) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    now = [instant("2025-01-01T08:00:00")]
    scans = ScanService(auth.engine, registry(), clock=lambda: now[0])
    schedules = ScheduleService(scans)
    data = ScheduleInput(
        label="Synthetic schedule",
        handler_key="synthetic",
        config={"count": 2},
        timezone="UTC",
        cadence="daily",
        local_time="09:00",
        lookback_days=1,
        request_id="schedule",
    )
    saved = schedules.create(actor, data)
    assert saved == schedules.create(actor, data)
    assert schedules.list(bob)["items"] == []
    with pytest.raises(MemoryError):
        schedules.toggle(bob, saved["id"], saved["revision"], False)
    # Three missed days dispatch only the latest occurrence, once.
    now[0] = instant("2025-01-04T12:00:00")
    assert schedules.dispatch() == 1
    assert schedules.dispatch() == 0
    dispatched = schedules.list(actor)["items"][0]
    assert dispatched["next_run"] == instant("2025-01-05T09:00:00")
    first = dispatched["last_run_id"]
    assert len(scans.list(actor)["items"]) == 1
    # Same resource still queued: record a skipped occurrence and advance.
    now[0] = instant("2025-01-05T10:00:00")
    assert schedules.dispatch() == 1
    overlap = schedules.list(actor)["items"][0]
    assert overlap["last_status"] == "skipped_overlap"
    assert overlap["last_run_id"] == first
    assert len(scans.list(actor)["items"]) == 1
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, first)["imported"] == 2
    paused = schedules.toggle(actor, saved["id"], saved["revision"], False)
    with pytest.raises(MemoryError):
        schedules.toggle(actor, saved["id"], saved["revision"], True)
    now[0] = instant("2025-01-10T12:00:00")
    assert schedules.dispatch() == 0
    resumed = schedules.toggle(actor, saved["id"], paused["revision"], True)
    assert resumed["next_run"] > now[0]
    auth.engine.dispose()


def test_schedule_caps_replay_conflicts_and_paused_edits(tmp_path: Path) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    now = [instant("2025-01-01T08:00:00")]
    scans = ScanService(auth.engine, registry(), clock=lambda: now[0])
    schedules = ScheduleService(scans)
    data = ScheduleInput(
        label="Synthetic",
        handler_key="synthetic",
        config={},
        timezone="UTC",
        cadence="daily",
        local_time="09:00",
        lookback_days=1,
        request_id="first",
    )
    first = schedules.create(actor, data)
    with pytest.raises(MemoryError, match="conflict"):
        schedules.create(actor, data.model_copy(update={"label": "Changed"}))
    for index in range(4):
        schedules.create(actor, data.model_copy(update={"request_id": str(index)}))
    with pytest.raises(MemoryError, match="limit"):
        schedules.create(actor, data.model_copy(update={"request_id": "sixth"}))
    assert schedules.create(bob, data)["id"] != first["id"]
    paused = schedules.toggle(actor, first["id"], 1, False)
    updated = schedules.edit(
        actor,
        first["id"],
        paused["revision"],
        data.model_copy(update={"label": "Changed"}),
    )
    assert not updated["enabled"] and updated["last_status"] == "paused"
    auth.engine.dispose()
