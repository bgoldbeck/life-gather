import asyncio
from pathlib import Path

import pytest
from test_reconciliation import setup
from test_scans import SyntheticHandler, registry

from lifegather.auth.store import AuthStore
from lifegather.memory.backup import operator_snapshot
from lifegather.scans.registry import ScanContext
from lifegather.scans.service import LeaseLost, ScanCanceled, ScanService
from lifegather.scans.worker import ScanWorker


def test_cancel_keeps_saved_evidence_and_snapshot_resumes(tmp_path: Path) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    now = [100]
    scans = ScanService(auth.engine, registry(), clock=lambda: now[0])
    run = scans.enqueue(actor, "synthetic", {}, "snapshot")
    claim = scans.claim()
    assert claim is not None
    batch = asyncio.run(
        SyntheticHandler().step(
            ScanContext(actor, run["id"], lambda: None), claim.config, claim.cursor
        )
    )
    scans.commit_batch(claim, batch)
    snapshot = tmp_path / "scan-snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    now[0] = 161
    copied = ScanService(restored.engine, registry(), clock=lambda: now[0])
    asyncio.run(ScanWorker(copied).run_once())
    assert copied.get(actor, run["id"])["imported"] == 3
    scans.cancel(actor, run["id"])
    with pytest.raises(LeaseLost):
        scans.commit_batch(claim, batch)
    assert scans.claim() is None
    assert scans.get(actor, run["id"])["state"] == "canceled"
    assert len(memory.export_page(actor, "sources")["items"]) == 1
    another = scans.enqueue(actor, "synthetic", {}, "cancel-active")
    active = scans.claim()
    assert active is not None
    scans.cancel(actor, another["id"])
    with pytest.raises(ScanCanceled):
        scans.heartbeat(active.id, active.token)
    scans.finish(active, "canceled")
    assert scans.get(actor, another["id"])["state"] == "canceled"
    restored.engine.dispose()
    auth.engine.dispose()


def test_scan_http_and_mcp_are_owner_bound_and_csrf_protected() -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import rpc, signed_headers

    from lifegather.main import create_app

    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "scan-alice")
        bob, _ = signed_headers(app, "scan-bob")
        app.state.scan_service.registry = registry()
        assert client.get("/api/scans").status_code == 401
        body = {"handler_key": "synthetic", "config": {}, "request_id": "http"}
        assert (
            client.post(
                "/api/scans", headers={"Cookie": alice["Cookie"]}, json=body
            ).status_code
            == 403
        )
        created = client.post("/api/scans", headers=alice, json=body)
        assert created.status_code == 200, created.text
        identifier = created.json()["id"]
        assert client.get("/api/scans/" + identifier, headers=bob).status_code == 400
        assert (
            client.post(
                "/api/scans/" + identifier + "/cancel", headers=bob, json={}
            ).status_code
            == 400
        )
        assert client.get("/api/scans", headers=bob).json()["items"] == []
        allowed = rpc(client, alice, "scan_get", {"run_id": identifier}).json()
        assert not allowed["result"].get("isError")
        assert "lease_token" not in str(allowed) and "cursor_json" not in str(allowed)
        assert rpc(client, bob, "scan_get", {"run_id": identifier}).json()["result"][
            "isError"
        ]
        assert (
            client.post("/api/scans", headers=alice, content=b"x" * 32769).status_code
            == 413
        )
        assert (
            client.post(
                "/api/scans/" + identifier + "/cancel", headers=alice, json={}
            ).status_code
            == 200
        )
        assert app.state.scan_service.list(actor)["items"][0]["cancel_requested"]
