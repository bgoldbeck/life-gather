import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx2
import pytest
from database_support import restore_copy
from pydantic import SecretStr, ValidationError
from test_mailboxes import provider
from test_reconciliation import setup
from test_scan_schedules import instant
from test_scans import registry

from lifegather.auth.store import AuthStore
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.service import MemoryError
from lifegather.scans.recurrence import next_occurrence
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker

pytestmark = pytest.mark.usefixtures("configured_database")


def test_weekly_half_hour_quarter_hour_and_invalid_configuration() -> None:
    # Monday 09:00 in Nepal (+05:45).
    assert next_occurrence(
        instant("2025-01-05T00:00:00"), "Asia/Kathmandu", "weekly", 0, "09:00"
    ) == instant("2025-01-06T03:15:00")
    # Lord Howe's spring gap is half an hour: 02:15 advances to 02:30.
    assert next_occurrence(
        instant("2025-10-04T12:00:00"), "Australia/Lord_Howe", "daily", 0, "02:15"
    ) == instant("2025-10-04T15:30:00")
    data: dict[str, Any] = dict(
        label="Synthetic",
        handler_key="synthetic",
        config={},
        timezone="UTC",
        cadence="daily",
        local_time="09:00",
        lookback_days=1,
        request_id="id",
    )
    for invalid in (
        {"timezone": "../etc/passwd"},
        {"timezone": "not-a-zone"},
        {"local_time": "24:00"},
        {"lookback_days": 31},
        {"weekday": 7},
    ):
        with pytest.raises((ValidationError, MemoryError)):
            ScheduleInput.model_validate({**data, **invalid})


def test_dispatch_concurrency_snapshot_and_edit_revision(tmp_path: Path) -> None:
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
        request_id="start",
    )
    saved = schedules.create(actor, data)
    updated = schedules.edit(
        actor, saved["id"], 1, data.model_copy(update={"local_time": "10:00"})
    )
    assert updated["revision"] == 2 and updated["next_run"] == instant(
        "2025-01-01T10:00:00"
    )
    with pytest.raises(MemoryError):
        schedules.edit(actor, saved["id"], 1, data)
    with pytest.raises(MemoryError):
        schedules.edit(bob, saved["id"], 2, data)
    snapshot = tmp_path / "schedule-snapshot.jsonl"
    operator_snapshot(auth.engine, snapshot)
    now[0] = instant("2025-01-01T11:00:00")
    with ThreadPoolExecutor(max_workers=2) as pool:
        dispatched = list(pool.map(lambda _: schedules.dispatch(), range(2)))
    assert sum(dispatched) == 1
    assert len(scans.list(actor)["items"]) == 1
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    copied_scans = ScanService(restored.engine, registry(), clock=lambda: now[0])
    copied = ScheduleService(copied_scans)
    # Restored before dispatch: the normal worker dispatches and consumes it.
    asyncio.run(ScanWorker(copied_scans, copied.dispatch).run_once())
    assert copied.list(actor)["items"][0]["last_run_id"] is not None
    assert copied_scans.list(actor)["items"][0]["state"] == "completed"
    assert copied.dispatch() == 0
    restored.engine.dispose()
    auth.engine.dispose()


def test_mailbox_revision_blocks_schedule_until_explicit_resume(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"r" * 32)
    mailboxes = Mailboxes(auth.engine, vault)
    grant = GmailGrant(
        address="synthetic@example.test", refresh_token=SecretStr("synthetic")
    )
    mailbox = mailboxes.connect(actor, grant)
    now = [instant("2025-01-01T08:00:00")]
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        data: dict[str, Any] = (
            {"access_token": "synthetic"}
            if request.url.host == "oauth2.googleapis.com"
            else {"emailAddress": "synthetic@example.test"}
            if request.url.path.endswith("profile")
            else {"messages": []}
        )
        return httpx2.Response(200, json=data)

    scans = ScanService(
        auth.engine,
        ScanRegistry(
            [
                GmailImportHandler(
                    auth.engine, vault, provider(httpx2.MockTransport(respond))
                )
            ]
        ),
        clock=lambda: now[0],
    )
    schedules = ScheduleService(scans)
    data = ScheduleInput(
        label="Mail",
        handler_key="gmail_import",
        config={"mailbox_id": mailbox["id"], "query": "receipt", "max_messages": 4},
        timezone="UTC",
        cadence="daily",
        local_time="09:00",
        lookback_days=2,
        request_id="start",
    )
    saved = schedules.create(actor, data)
    mailboxes.connect(actor, grant)
    now[0] = instant("2025-01-01T10:00:00")
    assert schedules.dispatch() == 1
    blocked = schedules.list(actor)["items"][0]
    assert blocked["enabled"] is False and blocked["last_status"] == "blocked"
    assert seen == [] and scans.list(actor)["items"] == []
    resumed = schedules.toggle(actor, saved["id"], blocked["revision"], True)
    assert resumed["scope"]["mailbox_revision"] == 2
    now[0] = instant("2025-01-02T10:00:00")
    asyncio.run(ScanWorker(scans, schedules.dispatch).run_once())
    run = scans.list(actor)["items"][0]
    assert run["state"] == "completed"
    assert run["scope"]["until_timestamp"] == instant("2025-01-02T09:00:00")
    assert run["scope"]["from_timestamp"] == instant("2024-12-31T09:00:00")
    assert any("receipt" in url for url in seen)
    auth.engine.dispose()


def test_schedule_api_and_mcp_are_private_and_writes_require_csrf() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "schedule-alice")
        bob, _ = signed_headers(app, "schedule-bob")
        app.state.scan_service.registry = registry()
        body = dict(
            label="Synthetic",
            handler_key="synthetic",
            config={},
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=1,
            request_id="create",
        )
        assert client.get("/api/scan-schedules").status_code == 401
        assert (
            client.post(
                "/api/scan-schedules", headers={"Cookie": alice["Cookie"]}, json=body
            ).status_code
            == 403
        )
        created = client.post("/api/scan-schedules", headers=alice, json=body)
        assert created.status_code == 200, created.text
        identifier = created.json()["id"]
        toggle = {"expected_revision": 1, "enabled": False}
        assert (
            client.post(
                f"/api/scan-schedules/{identifier}/toggle", headers=bob, json=toggle
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/scan-schedules/{identifier}/toggle", headers=alice, json=toggle
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/scan-schedules/{identifier}/toggle", headers=alice, json=toggle
            ).status_code
            == 409
        )
        assert client.get("/api/scan-schedules", headers=bob).json()["items"] == []
        assert "Synthetic" in str(rpc(client, alice, "scan_schedule_list", {}).json())
        assert "Synthetic" not in str(rpc(client, bob, "scan_schedule_list", {}).json())
        assert (
            client.post(
                "/api/scan-schedules", headers=alice, content=b"x" * 32769
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/scan-schedules",
                headers=alice,
                json={**body, "timezone": "bad-zone"},
            ).status_code
            == 422
        )
