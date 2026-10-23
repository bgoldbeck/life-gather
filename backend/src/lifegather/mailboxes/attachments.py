"""Bounded Gmail attachment intake as reviewable documents and private photos.

Only supported document and image files within fixed limits are downloaded.
Document text is extracted locally by the document service and images go through
the normal photo upload; nothing is sent to an AI provider, no asset is created,
and nothing becomes evidence until the user reviews it.
"""

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.formats import MIMES
from lifegather.documents.models import Document
from lifegather.documents.service import DocumentService
from lifegather.mailboxes.discovery_models import EmailAttachment
from lifegather.mailboxes.provider import (
    GMAIL_URL,
    GmailProvider,
    MailboxFailure,
    MailboxReconnect,
)
from lifegather.mailboxes.scan import GmailImportHandler, GmailScanConfig
from lifegather.mailboxes.text import message_text
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.photos.models import Photo
from lifegather.photos.service import MAX_BYTES as MAX_IMAGE_BYTES
from lifegather.photos.service import PhotoService
from lifegather.scans.registry import ScanContext, ScanEvidence

MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
IMAGES = frozenset({"jpg", "jpeg", "png", "webp"})
MAX_ATTACHMENTS = 3
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,2048}")


class GmailAttachmentConfig(GmailScanConfig):
    max_messages: int = Field(default=10, ge=1, le=20)


@dataclass(frozen=True)
class AttachmentPart:
    part_id: str
    filename: str
    size: int
    attachment_id: str
    inline: str
    kind: Literal["document", "photo"] = "document"


def safe_filename(value: Any) -> str:
    name = "".join(
        "_" if c in "/\\" else c for c in str(value) if ord(c) >= 32 and c != "\x7f"
    ).strip()
    if "." not in name:
        return name[:200]
    stem, extension = name.rsplit(".", 1)
    return stem[: 199 - len(extension)] + "." + extension


def attachment_parts(
    payload: dict[str, Any],
) -> tuple[list[AttachmentPart], list[tuple[str, str]]]:
    """Supported candidates, and skipped files with a reason; nothing is fetched."""
    candidates: list[AttachmentPart] = []
    skipped: list[tuple[str, str]] = []
    stack = [(payload, 0)]
    visited = 0
    while stack and visited < 100:
        part, depth = stack.pop()
        visited += 1
        children = part.get("parts", [])
        if depth < 10 and isinstance(children, list):
            stack.extend(
                (child, depth + 1)
                for child in reversed(children[:100])
                if isinstance(child, dict)
            )
        filename = safe_filename(part.get("filename") or "")
        body = part.get("body", {})
        if not filename or not isinstance(body, dict):
            continue
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        size = body.get("size")
        part_id = str(part.get("partId", ""))[:50] or str(visited)
        attachment_id = body.get("attachmentId", "")
        inline = body.get("data", "")
        photo = extension in IMAGES
        limit = MAX_IMAGE_BYTES if photo else MAX_ATTACHMENT_BYTES
        if extension not in MIMES and not photo:
            skipped.append((filename, "unsupported type"))
        elif not isinstance(size, int) or not 0 < size <= limit:
            skipped.append((filename, f"larger than {limit // 1048576} MiB"))
        elif len(candidates) >= MAX_ATTACHMENTS:
            skipped.append((filename, "attachment limit reached"))
        elif not (
            (isinstance(attachment_id, str) and IDENTIFIER.fullmatch(attachment_id))
            or (isinstance(inline, str) and inline and not attachment_id)
        ):
            skipped.append((filename, "unreadable attachment"))
        else:
            candidates.append(
                AttachmentPart(
                    part_id,
                    filename,
                    size,
                    attachment_id if isinstance(attachment_id, str) else "",
                    inline if isinstance(inline, str) else "",
                    "photo" if photo else "document",
                )
            )
    if stack:
        skipped.append(("further message parts", "part limit reached"))
    return candidates, skipped


def decode(data: Any, size: int) -> bytes:
    if not isinstance(data, str) or len(data) > (MAX_IMAGE_BYTES * 4) // 3 + 8:
        raise ValueError("Attachment data exceeds its limit")
    try:
        raw = base64.b64decode(
            data + "=" * (-len(data) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError):
        raise ValueError("Attachment data is not valid base64") from None
    if len(raw) != size or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Attachment size does not match its message")
    return raw


class GmailAttachmentHandler(GmailImportHandler):
    key = "gmail_attachments"
    title = "Import Gmail attachments"
    permissions = (*GmailImportHandler.permissions, "stored_documents", "photos")
    config_model = GmailAttachmentConfig

    def __init__(
        self,
        engine: Engine,
        vault: PrivateSettings,
        provider: GmailProvider,
        documents: DocumentService,
        photos: PhotoService,
    ) -> None:
        super().__init__(engine, vault, provider)
        self.documents = documents
        self.photos = photos

    async def evidence(
        self,
        context: ScanContext,
        config: dict[str, Any],
        identity: tuple[str, str, bytes],
        identifier: str,
        message: dict[str, Any],
        token: str,
        check: Callable[[], tuple[str, str, bytes]],
    ) -> ScanEvidence:
        parts = self.message_parts(config, identity, identifier, message)
        if parts is None:
            return ScanEvidence(
                identifier, None, "Gmail message", "Message outside requested dates"
            )
        label, header, payload = parts
        candidates, skipped = attachment_parts(payload)
        # The saved email text depends only on the message, never on this run's
        # download/quota outcome, so a later replay keeps one source identity.
        lines = [f"Attachment: {part.filename}" for part in candidates] + [
            f"Attachment not imported ({why}): {name}" for name, why in skipped
        ]
        saved: list[dict[str, str]] = []
        for part in candidates:
            check()
            try:
                data: Any = part.inline
                if part.attachment_id:
                    reply = await self.provider.request(
                        "GET",
                        f"{GMAIL_URL}/messages/{identifier}/attachments/"
                        + part.attachment_id,
                        token=token,
                    )
                    data = reply.get("data")
                raw = decode(data, part.size)
            except MailboxReconnect:
                raise
            except (MailboxFailure, ValueError):
                skipped.append((part.filename, "could not be downloaded"))
                continue
            check()
            try:
                if part.kind == "photo":
                    stored = self.photos.upload(context.actor, raw, part.filename)
                else:
                    stored = self.documents.upload(context.actor, raw, part.filename)
            except MemoryError as error:
                skipped.append((part.filename, str(error)[:100]))
                continue
            saved.append(
                {
                    "part_id": part.part_id,
                    "filename": part.filename,
                    part.kind + "_id": stored["id"],
                }
            )
        metadata: dict[str, str | int | bool] = {
            "attachments_saved": len(saved),
            "photos_saved": sum("photo_id" in value for value in saved),
            "attachments_skipped": len(skipped),
        }
        if not saved:
            return ScanEvidence(
                identifier,
                None,
                label,
                "No supported attachment within limits"
                if skipped
                else "No attachments",
                metadata,
            )
        listing = "\n".join(lines)[:1500]
        text, _ = message_text(payload)
        available = max(0, 3900 - len(header) - len(listing))
        body = header + "\n\n" + listing
        if text and available > 40:
            body += "\n\n" + text[: available - 20]
            if len(text) > available - 20:
                body += "\n[Text truncated]"
        source = SourceInput(
            text=body,
            source_type="email",
            namespace="gmail-attachments:" + config["mailbox_id"],
            external_id=identifier,
        )
        return ScanEvidence(
            identifier, source, label, "", metadata, {"attachments": saved}
        )

    def commit_in(
        self,
        db: Session,
        actor: Account,
        config: dict[str, Any],
        source_id: str,
        item: ScanEvidence,
    ) -> dict[str, str | int | bool]:
        self.authorize(db, actor, config)
        linked = 0
        for value in item.processing.get("attachments", [])[:MAX_ATTACHMENTS]:
            # Each link names exactly one stored file: a document or a photo.
            photo = "photo_id" in value
            target: type[Photo] | type[Document] = Photo if photo else Document
            column = EmailAttachment.photo_id if photo else EmailAttachment.document_id
            identifier = value["photo_id" if photo else "document_id"]
            stored = db.scalar(
                select(target.id).where(
                    target.user_id == actor.id,
                    target.id == identifier,
                    target.deleted_at.is_(None),
                )
            )
            if stored is None:
                continue
            if db.scalar(
                select(EmailAttachment.id).where(
                    EmailAttachment.user_id == actor.id,
                    EmailAttachment.source_id == source_id,
                    EmailAttachment.part_id == value["part_id"],
                    column == stored,
                )
            ):
                continue
            db.add(
                EmailAttachment(
                    id=str(uuid4()),
                    user_id=actor.id,
                    source_id=source_id,
                    document_id=None if photo else stored,
                    photo_id=stored if photo else None,
                    mailbox_id=config["mailbox_id"],
                    message_id=item.key,
                    part_id=value["part_id"],
                    filename=value["filename"],
                    recorded_at=self.documents.memory.clock(),
                )
            )
            linked += 1
        return {"attachments_linked": linked}
