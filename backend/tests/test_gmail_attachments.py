import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stored_files import files
from test_mailboxes import provider
from test_reconciliation import setup

from lifegather.credentials.service import PrivateSettings
from lifegather.documents.models import Document
from lifegather.documents.service import DocumentService
from lifegather.mailboxes.attachments import (
    MAX_ATTACHMENT_BYTES,
    GmailAttachmentHandler,
    attachment_parts,
    decode,
    safe_filename,
)
from lifegather.mailboxes.discovery_models import EmailAttachment
from lifegather.mailboxes.provider import GmailGrant, MailboxFailure
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.service import MemoryError
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker

RECEIPT = b"Synthetic order receipt for a cordless drill. Order A100."


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def message(identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "internalDate": "150000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "Subject", "value": "Synthetic order"}],
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "body": {"data": encoded(b"Your receipt is attached.")},
                },
                {
                    "partId": "1",
                    "filename": "receipt.txt",
                    "mimeType": "text/plain",
                    "body": {"attachmentId": "att-receipt", "size": len(RECEIPT)},
                },
                {
                    "partId": "2",
                    "filename": "photo.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "att-photo", "size": 2000},
                },
                {
                    "partId": "3",
                    "filename": "manual.pdf",
                    "mimeType": "application/pdf",
                    "body": {
                        "attachmentId": "att-large",
                        "size": MAX_ATTACHMENT_BYTES + 1,
                    },
                },
            ],
        },
    }


def test_attachment_intake_saves_documents_once_with_provenance(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"g" * 32)
    mailbox = Mailboxes(auth.engine, vault).connect(
        actor,
        GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic")),
    )
    fetched: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        fetched.append(path)
        if request.url.host == "oauth2.googleapis.com":
            data: dict[str, Any] = {"access_token": "synthetic-access"}
        elif path.endswith("profile"):
            data = {"emailAddress": "owner@example.test"}
        elif path.endswith("messages"):
            data = {"messages": [{"id": "abc123"}, {"id": "plain"}]}
        elif "/attachments/" in path:
            assert path.endswith("/messages/abc123/attachments/att-receipt")
            data = {"size": len(RECEIPT), "data": encoded(RECEIPT)}
        elif path.endswith("plain"):
            data = {
                "id": "plain",
                "internalDate": "150000",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": encoded(b"No attachment here")},
                },
            }
        else:
            data = message("abc123")
        return httpx2.Response(200, json=data)

    documents = DocumentService(auth.engine, files(auth.engine))
    handler = GmailAttachmentHandler(
        auth.engine, vault, provider(httpx2.MockTransport(respond)), documents
    )
    scans = ScanService(auth.engine, ScanRegistry([handler]))
    scope = {
        "mailbox_id": mailbox["id"],
        "from_timestamp": 100,
        "until_timestamp": 200,
        "max_messages": 5,
    }
    for request_id, state in (("first", "saved"), ("repeat", "existing")):
        run = scans.enqueue(actor, "gmail_attachments", scope, request_id)
        asyncio.run(ScanWorker(scans).run_once())
        result = scans.get(actor, run["id"])
        assert result["state"] == "completed", result
        assert result["scanned"] == 2 and result["skipped"] == 1
        saved = next(i for i in result["items"] if i["source_id"])
        assert saved["state"] == state
        assert saved["metadata"]["attachments_saved"] == 1
        assert saved["metadata"]["attachments_skipped"] == 2
        assert saved["metadata"]["attachments_linked"] == int(state == "saved")
    # Unsupported and oversized files are listed but never downloaded.
    assert not any(p.endswith(("att-photo", "att-large")) for p in fetched)
    listed = documents.list(actor)["items"]
    assert len(listed) == 1 and listed[0]["filename"] == "receipt.txt"
    assert listed[0]["source_id"] is None  # Text needs review before evidence.
    assert documents.binary(actor, listed[0]["id"]) == RECEIPT
    detail = documents.get(actor, listed[0]["id"])
    source = memory.get_source(actor, detail["email_sources"][0]["source_id"])
    assert source.source_type == "email"
    assert "Attachment: receipt.txt" in source.text
    assert "Attachment not imported (unsupported type): photo.jpg" in source.text
    assert "Your receipt is attached." in source.text
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailAttachment)) == 1
        stored = db.scalar(select(Document.original_key))
        assert stored and files(auth.engine).get(stored) == RECEIPT
    assert documents.list(bob)["items"] == [] and scans.list(bob)["items"] == []
    assert reconcile.inventory(actor) == []
    with pytest.raises(MemoryError):
        documents.get(bob, listed[0]["id"])
    auth.engine.dispose()


def test_attachment_parts_and_decoding_stay_bounded() -> None:
    payload = message("abc123")["payload"]
    payload["parts"] += [
        {
            "partId": str(i),
            "filename": f"extra{i}.pdf",
            "body": {"attachmentId": f"x{i}", "size": 10},
        }
        for i in range(4, 8)
    ]
    candidates, skipped = attachment_parts(payload)
    assert [c.filename for c in candidates] == [
        "receipt.txt",
        "extra4.pdf",
        "extra5.pdf",
    ]
    assert ("extra6.pdf", "attachment limit reached") in skipped
    assert ("manual.pdf", "larger than 4 MiB") in skipped
    assert safe_filename("../a\x00b/c.pdf") == ".._ab_c.pdf"
    assert len(safe_filename("x" * 300 + ".pdf")) == 200
    assert decode(encoded(b"abc"), 3) == b"abc"
    with pytest.raises(ValueError):
        decode(encoded(b"abc"), 4)
    with pytest.raises(ValueError):
        decode("not base64!", 3)


def test_attachment_endpoint_is_the_only_new_gmail_operation() -> None:
    gmail = provider(
        httpx2.MockTransport(lambda request: httpx2.Response(200, json={}))
    )
    base = "https://gmail.googleapis.com/gmail/v1/users/me/messages/abc"
    assert asyncio.run(gmail.request("GET", base + "/attachments/att-1")) == {}
    for method, url in (
        ("POST", base + "/attachments/att-1"),
        ("GET", base + "/attachments/../trash"),
        ("GET", base + "/modify"),
    ):
        with pytest.raises(MailboxFailure):
            asyncio.run(gmail.request(method, url))
