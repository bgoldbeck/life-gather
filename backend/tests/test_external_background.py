import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session
from test_reconciliation import setup
from test_scans import SyntheticHandler, registry

from lifegather import jobs
from lifegather.config import Settings
from lifegather.main import create_app
from lifegather.memory.history import event_origin
from lifegather.scans.models import ScanRun, ScanSchedule
from lifegather.scans.registry import ScanBatch, ScanContext, ScanRegistry
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker

pytestmark = pytest.mark.usefixtures("configured_database")

TOKEN = "synthetic-tick-token-0123456789abcdef"


class SlowHandler(SyntheticHandler):
    async def step(
        self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
    ) -> ScanBatch:
        await asyncio.sleep(1.2)
        return await super().step(context, config, cursor)


def schedule(scans: ScanService, actor: Any, count: int) -> dict[str, Any]:
    saved = ScheduleService(scans).create(
        actor,
        ScheduleInput(
            label="Synthetic schedule",
            handler_key="synthetic",
            config={"count": count},
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=1,
            request_id="external",
        ),
    )
    # Make the saved schedule due now instead of waiting for the next 09:00.
    with Session(scans.engine) as db, db.begin():
        db.execute(
            update(ScanSchedule)
            .where(ScanSchedule.id == saved["id"])
            .values(next_run=0)
        )
    return saved


def test_tick_settings_validate_mode_and_token() -> None:
    assert Settings().background_mode == "inprocess"
    assert not Settings(job_tick_token=SecretStr(TOKEN)).tick_endpoint_enabled
    assert Settings(
        background_mode="external", job_tick_token=SecretStr(TOKEN)
    ).tick_endpoint_enabled
    for bad in ("short-token", "x" * 31, "x" * 31 + " ", "x" * 31 + "é"):
        with pytest.raises(ValidationError) as error:
            Settings(job_tick_token=SecretStr(bad))
        assert bad not in str(error.value)
    with pytest.raises(ValidationError):
        Settings(background_mode="cron")  # type: ignore[arg-type]


def test_tick_dispatches_and_resumes_long_scans_at_the_limit(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    scans = ScanService(auth.engine, ScanRegistry([SlowHandler()]))
    saved = schedule(scans, actor, 3)
    worker = jobs.scan_worker(scans)

    # The first step outlasts the limit, so the run pauses after one record.
    first = asyncio.run(worker.tick(1))
    assert (first.dispatched, first.ran, first.paused) == (1, 0, 1)
    assert first.stopped == "time_limit"
    run_id = ScheduleService(scans).list(actor)["items"][0]["last_run_id"]
    paused = scans.get(actor, run_id)
    assert paused["state"] == "queued" and paused["imported"] == 1
    with Session(auth.engine) as db:
        row = db.get(ScanRun, run_id)
        assert row is not None and row.attempts == 0 and row.lease_token is None

    second = asyncio.run(worker.tick(10))
    assert (second.dispatched, second.ran, second.paused) == (0, 1, 0)
    assert second.stopped == "idle"
    done = scans.get(actor, run_id)
    assert done["state"] == "completed" and done["imported"] == 3
    assert ScheduleService(scans).list(actor)["items"][0]["id"] == saved["id"]
    # An empty queue returns at once.
    assert asyncio.run(worker.tick(5)).stopped == "idle"
    auth.engine.dispose()


def test_external_mode_starts_no_loop_and_guards_the_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served: list[bool] = []

    async def recorded(self: ScanWorker) -> None:
        served.append(True)
        await asyncio.Event().wait()

    monkeypatch.setattr(ScanWorker, "serve", recorded)
    with TestClient(create_app()) as client:
        # In-process default: the loop runs and there is no tick endpoint.
        assert served == [True]
        assert (
            client.post(
                "/internal/jobs/tick", headers={"Authorization": f"Bearer {TOKEN}"}
            ).status_code
            == 404
        )

    served.clear()
    monkeypatch.setenv("LIFEGATHER_BACKGROUND_MODE", "external")
    with TestClient(create_app()) as client:
        # External without a token: no loop, CLI only.
        assert served == []
        assert client.post("/internal/jobs/tick").status_code == 404

    monkeypatch.setenv("LIFEGATHER_JOB_TICK_TOKEN", TOKEN)
    app = create_app()
    with TestClient(app) as client:
        assert served == []
        app.state.scan_service.registry = registry()
        url = "/internal/jobs/tick"
        for headers in (
            {},
            {"Authorization": TOKEN},
            {"Authorization": f"Bearer {TOKEN[:-1]}x"},
            {"Authorization": f"Basic {TOKEN}"},
        ):
            denied = client.post(url, headers=headers)
            assert denied.status_code == 401
            assert TOKEN not in denied.text
        good = {"Authorization": f"Bearer {TOKEN}"}
        assert client.post(url + "?seconds=0", headers=good).status_code == 422
        assert client.post(url + "?seconds=301", headers=good).status_code == 422
        assert client.post(url + "?seconds=²", headers=good).status_code == 422
        assert client.get(url, headers=good).status_code == 405

        auth = app.state.auth_store
        actor = auth.login("tick", "tick@example.test", "Tick", now=1).user
        saved = schedule(app.state.scan_service, actor, 2)
        response = client.post(url + "?seconds=5", headers=good)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json() == {
            "status": "ok",
            "dispatched": 1,
            "ran": 1,
            "paused": 0,
            "stopped": "idle",
        }
        run = app.state.scan_service.list(actor)["items"][0]
        assert run["state"] == "completed" and run["imported"] == 2
        with Session(auth.engine) as db:
            requested = event_origin(db, actor, run["id"], ("scan_requested",))
            queued = event_origin(db, actor, saved["id"], ("scan_schedule_queued",))
        assert requested is not None and requested["interface"] == "scheduler"
        # Not attributed to a web account request, though it arrived over HTTP.
        assert queued is not None and queued["interface"] == "service"
        assert queued["initiator"] == "unknown"

        class Busy:
            def locked(self) -> bool:
                return True

        app.state.tick_lock = Busy()
        assert client.post(url, headers=good).status_code == 409


def test_cli_runs_one_tick(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    auth, actor, _, _, _ = setup(tmp_path / "data")
    built = ScanService(auth.engine, registry())
    schedule(built, actor, 2)
    monkeypatch.setattr(jobs, "scan_service", lambda *args: built)
    assert jobs.main(["--seconds", "5"]) == 0
    assert "Queued 1 scheduled scans, finished 1" in capsys.readouterr().err
    assert built.list(actor)["items"][0]["state"] == "completed"
    with pytest.raises(SystemExit):
        jobs.main(["--seconds", "0"])
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", "")
    assert jobs.main([]) == 1
    assert "Tick failed" in capsys.readouterr().err
    auth.engine.dispose()
