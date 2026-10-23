import asyncio
import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx2
import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stored_files import files
from test_mailboxes import provider
from test_reconciliation import setup
from test_scan_schedules import instant

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
from lifegather.photos.models import Photo
from lifegather.photos.service import MAX_BYTES as MAX_IMAGE_BYTES
from lifegather.photos.service import PhotoList, PhotoService
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker

RECEIPT = b"Synthetic order receipt for a cordless drill. Order A100."


def jpeg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (40, 30), "green").save(out, format="JPEG")
    return out.getvalue()


PHOTO = jpeg()


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
                    "body": {"attachmentId": "att-photo", "size": len(PHOTO)},
                },
                {
                    "partId": "3",
                    "filename": "broken.png",
                    "mimeType": "image/png",
                    "body": {"data": encoded(b"not a png"), "size": 9},
                },
                {
                    "partId": "4",
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
        elif path.endswith("/messages/abc123/attachments/att-photo"):
            data = {"size": len(PHOTO), "data": encoded(PHOTO)}
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
    photos = PhotoService(auth.engine, files(auth.engine))
    handler = GmailAttachmentHandler(
        auth.engine,
        vault,
        provider(httpx2.MockTransport(respond)),
        documents,
        photos,
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
        assert saved["metadata"]["attachments_saved"] == 2
        assert saved["metadata"]["photos_saved"] == 1
        assert saved["metadata"]["attachments_skipped"] == 2
        assert saved["metadata"]["attachments_linked"] == 2 * (state == "saved")
    # Oversized files are listed but never downloaded.
    assert not any(p.endswith("att-large") for p in fetched)
    listed = documents.list(actor)["items"]
    assert len(listed) == 1 and listed[0]["filename"] == "receipt.txt"
    assert listed[0]["source_id"] is None  # Text needs review before evidence.
    assert documents.binary(actor, listed[0]["id"]) == RECEIPT
    detail = documents.get(actor, listed[0]["id"])
    source = memory.get_source(actor, detail["email_sources"][0]["source_id"])
    assert source.source_type == "email"
    assert "Attachment: receipt.txt" in source.text
    assert "Attachment: photo.jpg" in source.text
    assert "Attachment: broken.png" in source.text
    assert "Your receipt is attached." in source.text
    # The image is a private photo, linked to the same email, attached to nothing.
    pictures = photos.list(actor, PhotoList())["items"]
    assert [p["filename"] for p in pictures] == ["photo.jpg"]
    assert photos.binary(actor, pictures[0]["id"], True)[0] == PHOTO
    assert photos.assets(actor, pictures[0]["id"]) == ()
    assert photos.email_sources(actor, pictures[0]["id"]) == (
        {"source_id": source.id, "filename": "photo.jpg"},
    )
    with pytest.raises(MemoryError):
        photos.email_sources(bob, pictures[0]["id"])
    with Session(auth.engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailAttachment)) == 2
        assert db.scalar(select(func.count()).select_from(Photo)) == 1
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
        for i in range(5, 7)
    ]
    payload["parts"][2]["body"]["size"] = MAX_IMAGE_BYTES
    payload["parts"].insert(
        2,
        {
            "partId": "9",
            "filename": "Huge.JPEG",
            "body": {"attachmentId": "x9", "size": MAX_IMAGE_BYTES + 1},
        },
    )
    candidates, skipped = attachment_parts(payload)
    assert [(c.filename, c.kind) for c in candidates] == [
        ("receipt.txt", "document"),
        ("photo.jpg", "photo"),
        ("broken.png", "photo"),
    ]
    assert ("extra5.pdf", "attachment limit reached") in skipped
    assert ("manual.pdf", "larger than 4 MiB") in skipped
    assert ("Huge.JPEG", "larger than 8 MiB") in skipped
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


def test_scheduled_attachment_scan_saves_photos_within_limits(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"g" * 32)
    mailbox = Mailboxes(auth.engine, vault).connect(
        actor,
        GmailGrant(address="owner@example.test", refresh_token=SecretStr("synthetic")),
    )
    now = [instant("2025-01-01T08:00:00")]

    def respond(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if request.url.host == "oauth2.googleapis.com":
            data: dict[str, Any] = {"access_token": "synthetic-access"}
        elif path.endswith("profile"):
            data = {"emailAddress": "owner@example.test"}
        elif path.endswith("messages"):
            data = {"messages": [{"id": "abc123"}]}
        elif "/attachments/" in path:
            raw = PHOTO if path.endswith("att-photo") else RECEIPT
            data = {"size": len(raw), "data": encoded(raw)}
        else:
            data = message("abc123")
            data["internalDate"] = str((now[0] - 3600) * 1000)
        return httpx2.Response(200, json=data)

    photos = PhotoService(auth.engine, files(auth.engine))
    handler = GmailAttachmentHandler(
        auth.engine,
        vault,
        provider(httpx2.MockTransport(respond)),
        DocumentService(auth.engine, files(auth.engine)),
        photos,
    )
    scans = ScanService(auth.engine, ScanRegistry([handler]), clock=lambda: now[0])
    schedules = ScheduleService(scans)

    def schedule(request_id: str, max_messages: int) -> ScheduleInput:
        return ScheduleInput(
            label="Emailed receipts",
            handler_key="gmail_attachments",
            config={
                "mailbox_id": mailbox["id"],
                "query": "has:attachment",
                "max_messages": max_messages,
            },
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=1,
            request_id=request_id,
        )

    # Attachment schedules keep the tighter per-run message limit.
    with pytest.raises(MemoryError):
        schedules.create(actor, schedule("too-many", 21))
    saved = schedules.create(actor, schedule("daily", 20))
    assert saved["scope"]["max_messages"] == 20
    now[0] = instant("2025-01-01T09:30:00")
    assert schedules.dispatch() == 1
    run_id = schedules.list(actor)["items"][0]["last_run_id"]
    asyncio.run(ScanWorker(scans).run_once())
    result = scans.get(actor, run_id)
    assert result["handler_key"] == "gmail_attachments"
    assert result["state"] == "completed", result
    assert result["items"][0]["metadata"]["photos_saved"] == 1
    assert [p["filename"] for p in photos.list(actor, PhotoList())["items"]] == [
        "photo.jpg"
    ]
    assert photos.list(bob, PhotoList())["items"] == []
    auth.engine.dispose()
