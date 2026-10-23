"""Gmail is one registered source handler, independent of queue and recurrence."""

import re
import time
from collections.abc import Callable
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings, ReconnectRequired
from lifegather.mailboxes.provider import (
    GMAIL_URL,
    READ_SCOPE,
    GmailProvider,
    MailboxReconnect,
)
from lifegather.mailboxes.service import Mailboxes
from lifegather.mailboxes.text import message_text
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.scans.registry import PreparedScan, ScanBatch, ScanContext, ScanEvidence


class GmailScanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mailbox_id: str = Field(min_length=1, max_length=36)
    from_timestamp: int = Field(ge=0)
    until_timestamp: int = Field(gt=0)
    query: str = Field(default="", max_length=200)
    max_messages: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def window(self) -> Self:
        if not 0 < self.until_timestamp - self.from_timestamp <= 31 * 86400:
            raise ValueError("Choose a window of at most 31 days")
        if self.until_timestamp > int(time.time()) + 60:
            raise ValueError("Choose a past scan window")
        return self


class GmailImportHandler:
    key = "gmail_import"
    title = "Import Gmail evidence"
    permissions: tuple[str, ...] = (READ_SCOPE,)
    config_model: type[BaseModel] = GmailScanConfig

    def __init__(
        self, engine: Engine, vault: PrivateSettings, provider: GmailProvider
    ) -> None:
        self.engine, self.vault, self.provider = engine, vault, provider

    def validate(
        self, db: Session, actor: Account, config: dict[str, Any]
    ) -> tuple[str, str, bytes]:
        row = Mailboxes.owned(db, actor, config["mailbox_id"])
        credential = (
            db.get(Credential, row.credential_id) if row.credential_id else None
        )
        if (
            not self.vault.enabled
            or credential is None
            or credential.user_id != actor.id
            or credential.kind != "email"
            or credential.provider != "gmail"
            or row.revision != config.get("mailbox_revision", row.revision)
        ):
            raise MemoryError(
                "Mailbox changed or disconnected. Reconnect and request a new scan."
            )
        return row.address, credential.id, credential.nonce

    def prepare(self, actor: Account, config: BaseModel) -> PreparedScan:
        values = config.model_dump()
        with Session(self.engine) as db:
            self.validate(db, actor, values)
            values["mailbox_revision"] = Mailboxes.owned(
                db, actor, values["mailbox_id"]
            ).revision
        return PreparedScan("gmail:" + values["mailbox_id"], values)

    def window(self, config: dict[str, Any], since: int, until: int) -> dict[str, Any]:
        values = {
            key: value for key, value in config.items() if key != "mailbox_revision"
        }
        return {**values, "from_timestamp": since, "until_timestamp": until}

    def authorize(self, db: Session, actor: Account, config: dict[str, Any]) -> None:
        self.validate(db, actor, config)

    async def step(
        self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
    ) -> ScanBatch:
        try:
            return await self.gmail_step(context, config, cursor)
        except MailboxReconnect:
            identity = context.state.get("identity")
            if identity is not None:
                self.vault.record_auth(
                    context.actor,
                    identity[1],
                    "reconnect",
                    context.state.get("read_at", 0),
                )
            raise ReconnectRequired("gmail", config["mailbox_id"], "gmail") from None

    async def gmail_step(
        self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
    ) -> ScanBatch:
        def check() -> tuple[str, str, bytes]:
            context.check()
            with Session(self.engine) as db:
                identity = self.validate(db, context.actor, config)
            if "identity" in context.state and context.state["identity"] != identity:
                raise MemoryError("Mailbox authorization changed during scan")
            return identity

        identity = check()
        if "token" not in context.state:
            context.state["identity"] = identity
            context.state["read_at"] = read_at = int(time.time())
            token = await self.provider.access(
                self.vault.read_secret(context.actor, identity[1])
            )
            self.vault.record_auth(context.actor, identity[1], "working", read_at)
            check()
            profile = await self.provider.request(
                "GET", GMAIL_URL + "/profile", token=token
            )
            if str(profile.get("emailAddress", "")).lower() != identity[0]:
                raise MemoryError("Mailbox account no longer matches its connection")
            context.state["token"] = token
        token = context.state["token"]
        pending = list(cursor.get("pending", []))
        page = cursor.get("page", "")
        seen = int(cursor.get("seen", 0))
        if not pending:
            check()
            query = (
                f"after:{config['from_timestamp']} before:{config['until_timestamp']}"
            )
            if config["query"]:
                query += " (" + config["query"] + ")"
            params: dict[str, str | int] = {
                "q": query,
                "maxResults": min(10, config["max_messages"] - seen),
                "includeSpamTrash": "false",
            }
            if page:
                params["pageToken"] = page
            reply = await self.provider.request(
                "GET", GMAIL_URL + "/messages", token=token, params=params
            )
            messages = reply.get("messages", [])
            if not isinstance(messages, list) or len(messages) > 10:
                raise MemoryError("Invalid Gmail message listing")
            pending = [m.get("id") for m in messages if isinstance(m, dict)]
            if len(pending) != len(messages) or any(
                not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", i)
                for i in pending
            ):
                raise MemoryError("Invalid Gmail message identity")
            page = reply.get("nextPageToken", "")
            if not isinstance(page, str) or len(page) > 2048:
                raise MemoryError("Invalid Gmail page cursor")
            if not pending:
                check()
                return ScanBatch([], None, bool(page))
        identifier = pending.pop(0)
        check()
        message = await self.provider.request(
            "GET",
            GMAIL_URL + "/messages/" + identifier,
            token=token,
            params={"format": "full"},
        )
        check()
        evidence = await self.evidence(
            context, config, identity, identifier, message, token, check
        )
        seen += 1
        more = bool(pending or page)
        done = not more or seen >= config["max_messages"]
        return ScanBatch(
            [evidence],
            None if done else {"pending": pending, "page": page, "seen": seen},
            done and more,
        )

    @staticmethod
    def message_parts(
        config: dict[str, Any],
        identity: tuple[str, str, bytes],
        identifier: str,
        message: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]] | None:
        """Label, provenance header and payload of an in-window message."""
        try:
            timestamp = int(message.get("internalDate", "")) // 1000
        except (ValueError, TypeError):
            timestamp = -1
        payload = message.get("payload")
        if (
            message.get("id") != identifier
            or not config["from_timestamp"] <= timestamp < config["until_timestamp"]
            or not isinstance(payload, dict)
        ):
            return None
        headers = payload.get("headers", [])
        selected: dict[str, str] = {}
        if isinstance(headers, list):
            for h in headers[:100]:
                if isinstance(h, dict) and str(h.get("name", "")).lower() in {
                    "from",
                    "to",
                    "subject",
                    "date",
                }:
                    selected[str(h["name"]).lower()] = (
                        str(h.get("value", ""))[:300]
                        .replace("\r", " ")
                        .replace("\n", " ")
                    )
        label = selected.get("subject", "Gmail message")[:200]
        header = f"Mailbox: {identity[0]}\nGmail message: {identifier}\n" + "\n".join(
            f"{k}: {v}" for k, v in selected.items()
        )
        return label, header, payload

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
        source = None
        reason = "No supported text body, or message outside requested dates"
        metadata: dict[str, str | int | bool] = {}
        label = "Gmail message"
        parts = self.message_parts(config, identity, identifier, message)
        if parts is not None:
            label, header, payload = parts
            text, omitted = message_text(payload)
            if text:
                available = max(1, 3900 - len(header))
                truncated = len(text) > available
                body = (
                    header
                    + "\n\n"
                    + text[:available]
                    + ("\n[Text truncated]" if truncated else "")
                    + (
                        "\n[Attachments or unsupported parts omitted]"
                        if omitted
                        else ""
                    )
                )
                source = SourceInput(
                    text=body,
                    source_type="email",
                    namespace="gmail-memory:" + config["mailbox_id"],
                    external_id=identifier,
                )
                reason = ""
                metadata = {"truncated": truncated, "parts_omitted": omitted}
        return ScanEvidence(identifier, source, label, reason, metadata)
