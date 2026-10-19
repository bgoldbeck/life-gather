import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx2
from pydantic import SecretStr
from test_mailboxes import provider
from test_reconciliation import setup

from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.notes import NoteService
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker


def test_requested_gmail_text_import_replay_and_private_scope(tmp_path: Path) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"g" * 32)
    mailboxes = Mailboxes(auth.engine, vault)
    mailbox = mailboxes.connect(
        actor,
        GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic")),
    )
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.host == "oauth2.googleapis.com":
            data: dict[str, Any] = {"access_token": "synthetic-access"}
        elif request.url.path.endswith("profile"):
            data = {"emailAddress": "owner@example.test"}
        elif request.url.path.endswith("messages"):
            assert "after:100" in request.url.params["q"]
            assert "before:200" in request.url.params["q"]
            data = {"messages": [{"id": "abc123"}, {"id": "outside"}]}
        else:
            data = {
                "id": request.url.path.rsplit("/", 1)[1],
                "internalDate": "150000"
                if request.url.path.endswith("abc123")
                else "999000",
                "payload": {
                    "mimeType": "text/html",
                    "headers": [{"name": "Subject", "value": "Synthetic receipt"}],
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b'<p>Synthetic item</p><script>do not execute</script><img src="https://example.test/track">'
                        ).decode()
                    },
                },
            }
        return httpx2.Response(200, json=data)

    handler = GmailImportHandler(
        auth.engine, vault, provider(httpx2.MockTransport(respond))
    )
    scans = ScanService(auth.engine, ScanRegistry([handler]))
    scope = {
        "mailbox_id": mailbox["id"],
        "from_timestamp": 100,
        "until_timestamp": 200,
        "max_messages": 5,
    }
    for request_id in ("first", "repeat"):
        run = scans.enqueue(actor, "gmail_import", scope, request_id)
        asyncio.run(ScanWorker(scans).run_once())
        result = scans.get(actor, run["id"])
        assert result["state"] == "completed", result
        assert result["scanned"] == 2 and result["skipped"] == 1
    sources = memory.export_page(actor, "sources")["items"]
    assert len(sources) == 1
    source = memory.get_source(actor, sources[0]["id"])
    assert source.source_type == "email" and "Synthetic item" in source.text
    assert (
        "do not execute" not in source.text
        and "https://example.test/track" not in source.text
    )
    assert NoteService(auth.engine).describe(actor, source.id) is not None
    assert reconcile.inventory(actor) == [] and scans.list(bob)["items"] == []
    assert {r.method for r in seen} == {"GET", "POST"}
    assert all(
        r.url.host in {"oauth2.googleapis.com", "gmail.googleapis.com"} for r in seen
    )
    auth.engine.dispose()
