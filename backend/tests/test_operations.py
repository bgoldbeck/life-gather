import io
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from database_support import database
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_mcp_http import signed_headers
from test_power_center import NOW, run

from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.database import account_scope
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.operations.logs import CAPTURE, configure_logging
from lifegather.operations.models import OperationalEvent
from lifegather.operations.monitor import OperationsMonitor
from lifegather.operations.service import pseudonym
from lifegather.scans.models import ScanSchedule

PRIVATE = "PRIVATE-receipt-from-dr-smith"
log = logging.getLogger("lifegather.tests")


@pytest.fixture(autouse=True)
def fresh_capture() -> None:
    CAPTURE.drain()


class Mail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.sent.append((recipient, subject, body))


def schedule(store: AuthStore, user_id: str, next_run: int) -> None:
    identifier = str(uuid4())
    with Session(store.engine) as db, db.begin():
        db.add(
            ScanSchedule(
                id=identifier,
                user_id=user_id,
                request_id=identifier,
                fingerprint=identifier,
                label="Weekly receipts",
                handler_key="gmail_import",
                config_json="{}",
                timezone="UTC",
                cadence="weekly",
                weekday=1,
                local_time="09:00",
                lookback_days=7,
                enabled=True,
                revision=1,
                next_run=next_run,
                last_due=None,
                last_run_id=None,
                last_status="never",
                created_at=NOW - 86400,
                updated_at=NOW - 86400,
            )
        )


def test_logs_and_events_leave_out_paths_queries_and_exception_text(
    tmp_path: Path,
) -> None:
    app = create_app()

    @app.get("/api/explode/{item_id}")
    def explode(item_id: str) -> None:
        raise ValueError(f"{PRIVATE} {item_id}")

    output = io.StringIO()
    with TestClient(app) as client:
        configure_logging(output)
        response = client.get(f"/api/explode/{PRIVATE}?q={PRIVATE}")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "Something went wrong"
        assert response.headers["x-request-id"] == body["request_id"]
        assert PRIVATE not in response.text
        client.get(f"/api/explode/other?q={PRIVATE}")
        assert client.get("/api/version").status_code == 200
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        failures = [line for line in lines if line["route"] == "/api/explode/{item_id}"]
        assert failures[0]["message"] == "Request failed unexpectedly"
        assert failures[0]["error_type"] == "ValueError"
        assert failures[0]["request_id"] == body["request_id"]
        assert any("explode" in frame for frame in failures[0]["location"])
        assert any(line.get("route") == "/api/version" for line in lines)
        assert PRIVATE not in output.getvalue()

        monitor: OperationsMonitor = app.state.operations_monitor
        assert monitor.flush() == 2
        with Session(app.state.auth_store.engine) as db:
            rows = list(db.scalars(select(OperationalEvent)))
        assert len(rows) == 1 and rows[0].count == 2
        assert json.loads(rows[0].detail_json) == {
            "error_type": "ValueError",
            "method": "GET",
            "route": "/api/explode/{item_id}",
        }
        assert rows[0].alerted_at is None  # no alert channel configured
        stored = json.dumps([rows[0].message, rows[0].detail_json, rows[0].logger])
        assert PRIVATE not in stored


def test_alerts_go_out_once_an_hour_without_private_content(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path / "alerts"))
    store.migrate()
    clock = [NOW]
    posts: list[tuple[str, dict[str, Any]]] = []
    mail = Mail()
    monitor = OperationsMonitor(
        store.engine,
        Settings(
            operator_emails="Ops@Example.test, second@example.test",
            alert_webhook_url="https://hooks.example.test/lifegather",
        ),
        mail,
        post=lambda url, payload: posts.append((url, payload)),
        clock=lambda: clock[0],
    )
    assert monitor.channels.webhook and monitor.channels.email

    def fail() -> None:
        try:
            raise RuntimeError(PRIVATE)
        except RuntimeError:
            log.exception("Nightly sweep failed", extra={"job": "sweep", "x": PRIVATE})

    fail()
    fail()
    assert monitor.flush() == 2
    assert len(posts) == 1 and len(mail.sent) == 2
    url, payload = posts[0]
    assert url == "https://hooks.example.test/lifegather"
    assert payload["message"] == "Nightly sweep failed"
    assert payload["details"] == {"error_type": "RuntimeError", "job": "sweep"}
    assert payload["count"] == 2 and "127.0.0.1:8787" in payload["text"]
    assert {recipient for recipient, _, _ in mail.sent} == {
        "ops@example.test",
        "second@example.test",
    }
    assert PRIVATE not in json.dumps(posts) + json.dumps(mail.sent)

    clock[0] += 600
    fail()
    monitor.flush()
    assert len(posts) == 1  # the same problem again within the hour
    clock[0] += 3600
    fail()
    monitor.flush()
    assert len(posts) == 2 and posts[1][1]["count"] == 4

    def refuse(url: str, payload: dict[str, Any]) -> None:
        raise httpx2.ConnectError("unreachable")

    monitor.post = refuse
    log.error("Another problem")
    assert monitor.flush() == 1  # delivery failure is logged, not raised


def test_stuck_jobs_raise_an_event_and_the_overview_counts_only(
    tmp_path: Path,
) -> None:
    store = AuthStore(database(tmp_path / "ops"))
    store.migrate()
    alice = store.login("ops-alice", "alice@example.test", "Alice", now=NOW).user
    bob = store.login("ops-bob", "bob@example.test", "Bob", now=NOW).user
    mailbox = {"id": "m1", "revision": 1}
    run(
        store, alice, mailbox, state="running", lease_until=NOW - 600, completed_at=None
    )
    run(
        store,
        bob,
        {"id": "m2", "revision": 1},
        state="queued",
        updated_at=NOW - 3600,
        completed_at=None,
    )
    run(store, bob, {"id": "m3", "revision": 1}, state="failed", error=PRIVATE)
    run(store, alice, {"id": "m4", "revision": 1}, state="completed")
    schedule(store, alice.id, NOW - 7200)
    schedule(store, bob.id, NOW + 3600)
    documents = DocumentService(store.engine, files(store.engine))
    with account_scope(alice.id):
        documents.upload(alice, synthetic_pdf(), "synthetic.pdf")

    monitor = OperationsMonitor(store.engine, Settings(), clock=lambda: NOW)
    stuck = monitor.check_jobs()
    assert (stuck.expired_leases, stuck.long_queued, stuck.overdue_schedules) == (
        1,
        1,
        1,
    )
    monitor.flush()
    overview = monitor.view().read()
    assert overview.jobs.running == 1 and overview.jobs.queued == 1
    assert overview.jobs.failed_7d == 1 and overview.jobs.completed_7d == 1
    assert [(group.handler, group.count) for group in overview.failures] == [
        ("gmail_import", 1)
    ]
    assert (overview.schedules.enabled, overview.schedules.paused) == (2, 0)
    assert overview.events[0].message == "Background jobs are stuck"
    assert overview.events[0].details == {"job": "scans"}
    assert overview.storage.accounts == 2 and overview.storage.documents == 1
    assert overview.storage.total_bytes == overview.storage.document_bytes > 0
    assert overview.storage.largest[0].account == pseudonym(alice.id)
    assert overview.storage.quota_bytes is None
    dumped = overview.model_dump_json()
    for private in (PRIVATE, alice.id, bob.id, "alice@example.test", "synthetic.pdf"):
        assert private not in dumped


def test_account_role_cannot_read_operational_events(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path / "role"))
    store.migrate()
    alice = store.login("role-alice", "alice@example.test", "Alice", now=NOW).user
    with account_scope(alice.id), Session(store.engine) as db:
        with pytest.raises(ProgrammingError):
            db.execute(text("SELECT count(*) FROM operational_events"))


def test_only_operators_can_open_the_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_OPERATOR_EMAILS", "ops-operator@example.test")
    app = create_app()
    with TestClient(app) as client:
        operator, _ = signed_headers(app, "ops-operator")
        member, _ = signed_headers(app, "ops-member")
        assert client.get("/api/operator/overview").status_code == 401
        assert client.get("/api/operator/access", headers=member).json() == {
            "operator": False
        }
        refused = client.get("/api/operator/overview", headers=member)
        assert refused.status_code == 404
        assert client.get("/api/operator/access", headers=operator).json() == {
            "operator": True
        }
        log.error("Captured before the page opened")
        allowed = client.get("/api/operator/overview", headers=operator)
        assert allowed.status_code == 200
        assert allowed.headers["cache-control"] == "no-store"
        data = allowed.json()
        assert data["storage"]["accounts"] == 2
        assert data["background_mode"] == "inprocess"
        assert data["alerts"] == {"webhook": False, "email": False}
        assert data["events"][0]["message"] == "Captured before the page opened"
        # The assistant beside the page accepts it as ordinary page context.
        page = client.post(
            "/api/chat/context",
            headers=operator,
            json={"page": "Operations", "entity_id": None},
        )
        assert page.status_code == 200


def test_alert_webhook_must_be_https() -> None:
    with pytest.raises(ValueError):
        Settings(alert_webhook_url="http://hooks.example.test/x")
    assert Settings(operator_emails=" A@x.test ,,b@x.test").operator_email_set == {
        "a@x.test",
        "b@x.test",
    }
