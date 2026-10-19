import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from test_mailboxes import provider
from test_reconciliation import setup
from test_scans import registry

from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.mailboxes.service import Mailboxes
from lifegather.mailboxes.text import message_text
from lifegather.memory.library import LibraryPage, MemoryLibrary
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker


@pytest.mark.parametrize(
    "changed", ["disconnect", "wrong_account", "bad_identity", "oversized"]
)
def test_gmail_failure_boundaries_never_save_wrong_or_revoked_evidence(
    tmp_path: Path, changed: str
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"b" * 32)
    mailboxes = Mailboxes(auth.engine, vault)
    mailbox = mailboxes.connect(
        actor,
        GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic")),
    )
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        data: dict[str, Any]
        if request.url.host == "oauth2.googleapis.com":
            data = {"access_token": "synthetic"}
        elif request.url.path.endswith("profile"):
            data = {
                "emailAddress": "someoneelse@example.test"
                if changed == "wrong_account"
                else "owner@example.test"
            }
        elif request.url.path.endswith("messages"):
            data = {
                "messages": [
                    {"id": "https://evil.test/" if changed == "bad_identity" else "abc"}
                ]
            }
        else:
            if changed == "disconnect":
                mailboxes.disconnect(actor, mailbox["id"], mailbox["revision"])
            if changed == "oversized":
                return httpx2.Response(200, content=b"x" * 524289)
            data = {
                "id": "abc",
                "internalDate": "150000",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"Synthetic receipt").decode()
                    },
                },
            }
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
    )
    run = scans.enqueue(
        actor,
        "gmail_import",
        {"mailbox_id": mailbox["id"], "from_timestamp": 100, "until_timestamp": 200},
        "boundary",
    )
    asyncio.run(ScanWorker(scans).run_once())
    result = scans.get(actor, run["id"])
    assert result["state"] == "failed" and result["scanned"] == 0
    assert memory.export_page(actor, "sources")["items"] == []
    assert "someoneelse" not in str(result) and "evil.test" not in str(result)
    assert all("evil.test" not in url for url in seen)
    assert (
        MemoryLibrary(auth.engine).list(actor, LibraryPage(kind="emails"))["items"]
        == []
    )
    auth.engine.dispose()


def test_mime_attachments_and_deep_parts_are_not_imported() -> None:
    data = base64.urlsafe_b64encode(b"Visible text").decode()
    text, omitted = message_text(
        {
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "secret.txt",
                    "body": {"data": data},
                },
                {"mimeType": "text/plain", "body": {"data": data}},
            ]
        }
    )
    assert text == "Visible text" and omitted
    text, _ = message_text({"mimeType": "text/plain", "body": {"data": "%%%invalid"}})
    assert text == ""


def test_recovery_limit_prevents_an_unbounded_retry_loop(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    now = [100]
    scans = ScanService(auth.engine, registry(), clock=lambda: now[0])
    run = scans.enqueue(actor, "synthetic", {}, "expired")
    for _ in range(3):
        assert scans.claim() is not None
        now[0] += 61
    assert scans.claim() is None
    assert scans.get(actor, run["id"])["state"] == "failed"
    auth.engine.dispose()
