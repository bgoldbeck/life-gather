"""Owner-bound mailbox grants and session-bound one-time consent flows."""

import hashlib
import secrets
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account, digest
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.models import Mailbox, MailboxFlow
from lifegather.mailboxes.provider import GmailGrant
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, MemoryService


class Mailboxes:
    def __init__(
        self,
        engine: Engine,
        vault: PrivateSettings,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.engine, self.vault = engine, vault
        self.clock = clock or (lambda: int(time.time()))
        self.memory = MemoryService(engine)

    def begin(
        self, actor: Account, session_token: str, browser: str
    ) -> tuple[str, str]:
        if not self.vault.enabled:
            raise MemoryError(
                "Configure encrypted credential storage before connecting mail"
            )
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        with self.memory._write() as db:
            db.execute(
                delete(MailboxFlow).where(
                    MailboxFlow.user_id == actor.id,
                    MailboxFlow.expires_at <= self.clock(),
                )
            )
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(MailboxFlow)
                    .where(MailboxFlow.user_id == actor.id)
                )
                or 0
            )
            if count >= 5:
                raise MemoryError(
                    "Too many pending mailbox connections. Try again later."
                )
            db.add(
                MailboxFlow(
                    state_hash=digest(state),
                    user_id=actor.id,
                    session_hash=digest(session_token),
                    browser_hash=digest(browser),
                    verifier=verifier,
                    expires_at=self.clock() + 600,
                )
            )
        return state, verifier

    def consume(
        self, actor: Account, session_token: str, browser: str, state: str
    ) -> str:
        with self.memory._write() as db:
            row = db.get(MailboxFlow, digest(state))
            if (
                row is None
                or row.user_id != actor.id
                or row.expires_at <= self.clock()
                or not secrets.compare_digest(row.session_hash, digest(session_token))
                or not secrets.compare_digest(row.browser_hash, digest(browser))
            ):
                raise MemoryError(
                    "Mailbox consent expired or belongs to a different session"
                )
            verifier = row.verifier
            db.delete(row)
            return verifier

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> Mailbox:
        row = db.scalar(
            select(Mailbox).where(Mailbox.user_id == actor.id, Mailbox.id == identifier)
        )
        if row is None:
            raise MemoryError("Mailbox not found")
        return row

    @staticmethod
    def view(row: Mailbox, needs_reconnect: bool = False) -> dict[str, Any]:
        return {
            "id": row.id,
            "provider": "gmail",
            "address": row.address,
            "connected": row.credential_id is not None,
            # Google refused this grant (expired or revoked) on its last use.
            "needs_reconnect": row.credential_id is not None and needs_reconnect,
            "revision": row.revision,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def list(self, actor: Account) -> list[dict[str, Any]]:
        with Session(self.engine) as db:
            return [
                self.view(row, state == "reconnect")
                for row, state in db.execute(
                    select(Mailbox, Credential.auth_state)
                    .outerjoin(
                        Credential,
                        (Credential.user_id == Mailbox.user_id)
                        & (Credential.id == Mailbox.credential_id),
                    )
                    .where(Mailbox.user_id == actor.id)
                    .order_by(Mailbox.created_at, Mailbox.id)
                    .limit(10)
                )
            ]

    def connect(self, actor: Account, value: GmailGrant) -> dict[str, Any]:
        grant = GmailGrant.model_validate(value)
        account_key = hashlib.sha256(grant.address.encode()).hexdigest()
        with self.memory._write() as db:
            row = db.scalar(
                select(Mailbox).where(
                    Mailbox.user_id == actor.id, Mailbox.account_key == account_key
                )
            )
            if (
                row is None
                and (
                    db.scalar(
                        select(func.count())
                        .select_from(Mailbox)
                        .where(Mailbox.user_id == actor.id)
                    )
                    or 0
                )
                >= 10
            ):
                raise MemoryError("Mailbox limit reached")
            now = self.clock()
            credential = (
                db.get(Credential, row.credential_id)
                if row and row.credential_id
                else None
            )
            if credential is None:
                if (
                    db.scalar(
                        select(func.count())
                        .select_from(Credential)
                        .where(Credential.user_id == actor.id)
                    )
                    or 0
                ) >= 100:
                    raise MemoryError("Credential limit reached")
                credential = Credential(
                    id=str(uuid4()),
                    user_id=actor.id,
                    kind="email",
                    provider="gmail",
                    label=grant.address,
                    created_at=now,
                    updated_at=now,
                )
                db.add(credential)
            elif (
                credential.user_id != actor.id
                or credential.kind != "email"
                or credential.provider != "gmail"
            ):
                raise MemoryError("Mailbox connection changed")
            self.vault._encrypt(
                actor, credential, grant.refresh_token.get_secret_value()
            )
            credential.updated_at = now
            # Consent and the profile read just succeeded with this grant.
            credential.auth_state, credential.auth_checked_at = "working", now
            db.flush()
            if row is None:
                row = Mailbox(
                    id=str(uuid4()),
                    user_id=actor.id,
                    credential_id=credential.id,
                    account_key=account_key,
                    address=grant.address,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.credential_id = credential.id
                row.revision += 1
                row.updated_at = now
            db.flush()
            self.memory._audit(db, actor, "mailbox_connected", row.id, now * 1000000)
            return self.view(row)

    def disconnect(
        self, actor: Account, identifier: str, expected_revision: int
    ) -> dict[str, Any]:
        with self.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.credential_id is None:
                return self.view(row)
            if row.revision != expected_revision:
                raise NoteConflict("Mailbox changed. Reload before disconnecting.")
            credential_id = row.credential_id
            row.credential_id = None
            row.revision += 1
            row.updated_at = self.clock()
            db.flush()
            db.execute(
                delete(Credential).where(
                    Credential.user_id == actor.id, Credential.id == credential_id
                )
            )
            self.memory._audit(
                db, actor, "mailbox_disconnected", row.id, row.updated_at * 1000000
            )
            return self.view(row)
