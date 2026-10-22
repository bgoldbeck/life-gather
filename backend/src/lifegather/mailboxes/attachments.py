"""Bounded Gmail attachment intake as reviewable original documents.

Only supported document files within fixed limits are downloaded. Their text is
extracted locally by the document service; nothing is sent to an AI provider and
nothing becomes evidence until the user reviews the document text.
"""

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
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
from lifegather.mailboxes.provider import GMAIL_URL, GmailProvider, MailboxFailure
from lifegather.mailboxes.scan import GmailImportHandler, GmailScanConfig
from lifegather.mailboxes.text import message_text
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.scans.registry import ScanContext, ScanEvidence

MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
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
        if extension not in MIMES:
            skipped.append((filename, "unsupported type"))
        elif not isinstance(size, int) or not 0 < size <= MAX_ATTACHMENT_BYTES:
            skipped.append((filename, "larger than 4 MiB"))
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
                )
            )
    if stack:
        skipped.append(("further message parts", "part limit reached"))
    return candidates, skipped


def decode(data: Any, size: int) -> bytes:
    if not isinstance(data, str) or len(data) > (MAX_ATTACHMENT_BYTES * 4) // 3 + 8:
        raise ValueError("Attachment data exceeds its limit")
    try:
        raw = base64.b64decode(
            data + "=" * (-len(data) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError):
        raise ValueError("Attachment data is not valid base64") from None
    if len(raw) != size or len(raw) > MAX_ATTACHMENT_BYTES:
        raise ValueError("Attachment size does not match its message")
    return raw


class GmailAttachmentHandler(GmailImportHandler):
    key = "gmail_attachments"
    title = "Import Gmail attachments"
    permissions = (*GmailImportHandler.permissions, "stored_documents")
    config_model = GmailAttachmentConfig

    def __init__(
        self,
        engine: Engine,
        vault: PrivateSettings,
        provider: GmailProvider,
        documents: DocumentService,
    ) -> None:
        super().__init__(engine, vault, provider)
        self.documents = documents

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
            except (MailboxFailure, ValueError):
                skipped.append((part.filename, "could not be downloaded"))
                continue
            check()
            try:
                document = self.documents.upload(context.actor, raw, part.filename)
            except MemoryError as error:
                skipped.append((part.filename, str(error)[:100]))
                continue
            saved.append(
                {
                    "part_id": part.part_id,
                    "filename": part.filename,
                    "document_id": document["id"],
                }
            )
        metadata: dict[str, str | int | bool] = {
            "attachments_saved": len(saved),
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
            document = db.scalar(
                select(Document.id).where(
                    Document.user_id == actor.id,
                    Document.id == value["document_id"],
                    Document.deleted_at.is_(None),
                )
            )
            if document is None:
                continue
            if db.scalar(
                select(EmailAttachment.id).where(
                    EmailAttachment.user_id == actor.id,
                    EmailAttachment.source_id == source_id,
                    EmailAttachment.part_id == value["part_id"],
                    EmailAttachment.document_id == document,
                )
            ):
                continue
            db.add(
                EmailAttachment(
                    id=str(uuid4()),
                    user_id=actor.id,
                    source_id=source_id,
                    document_id=document,
                    mailbox_id=config["mailbox_id"],
                    message_id=item.key,
                    part_id=value["part_id"],
                    filename=value["filename"],
                    recorded_at=self.documents.memory.clock(),
                )
            )
            linked += 1
        return {"attachments_linked": linked}
