"""Permanent deletion of one account: its rows, stored files and sign-ins."""

import logging
import secrets
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

from sqlalchemy import Engine, or_, select, text
from sqlalchemy.orm import Session

from lifegather.auth.email_models import EmailCredential
from lifegather.auth.email_service import EmailAuth, verify_password
from lifegather.auth.email_validation import email_key
from lifegather.auth.store import Account
from lifegather.database import account_scope, begin_serialized
from lifegather.documents.models import Document
from lifegather.photos.models import Photo
from lifegather.storage.base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)

# Every ordinary table in the application schema with a user_id column.
OWNED_TABLES = text(
    """
    SELECT c.relname FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema() AND c.relkind = 'r'
      AND a.attname = 'user_id' AND a.attnum > 0 AND NOT a.attisdropped
    """
)
FOREIGN_KEYS = text(
    """
    SELECT child.relname, parent.relname FROM pg_constraint k
    JOIN pg_class child ON child.oid = k.conrelid
    JOIN pg_class parent ON parent.oid = k.confrelid
    JOIN pg_namespace n ON n.oid = child.relnamespace
    WHERE k.contype = 'f' AND n.nspname = current_schema()
    """
)


class AccountDeletionError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class DeletionResult:
    rows: int
    files: int


def deletion_order(db: Session) -> list[str]:
    """Owned tables, each listed after every owned table that references it."""
    owned = set(db.scalars(OWNED_TABLES))
    referenced_by: dict[str, set[str]] = {table: set() for table in owned}
    for child, parent in db.execute(FOREIGN_KEYS):
        # A self-reference is satisfied by deleting the table's rows together.
        if child != parent and parent in owned:
            if child not in owned:
                raise AccountDeletionError(
                    f"Table {child} references account rows without an owner", 500
                )
            referenced_by[parent].add(child)
    try:
        return list(TopologicalSorter(referenced_by).static_order())
    except CycleError:
        raise AccountDeletionError("Account tables reference each other", 500) from None


def _stored_keys(db: Session, user_id: str) -> set[str]:
    keys: set[str | None] = set(
        db.scalars(
            select(Document.original_key).where(
                Document.user_id == user_id, Document.original_key.is_not(None)
            )
        )
    )
    for original, preview in db.execute(
        select(Photo.original_key, Photo.preview_key).where(
            Photo.user_id == user_id,
            or_(Photo.original_key.is_not(None), Photo.preview_key.is_not(None)),
        )
    ):
        keys.update((original, preview))
    return {key for key in keys if key is not None}


class AccountDeletion:
    """Framework-independent; HTTP is a thin authenticated adapter."""

    def __init__(
        self, engine: Engine, storage: ObjectStorage | None, email: EmailAuth
    ) -> None:
        self.engine = engine
        self.storage = storage
        self.email = email

    def _confirm(
        self, actor: Account, email: str, password: str | None, *, client: str, now: int
    ) -> None:
        if not secrets.compare_digest(
            email.strip().casefold().encode(), actor.email.strip().casefold().encode()
        ):
            raise AccountDeletionError("Type your account's email address to confirm")
        with Session(self.engine) as db:
            credential = db.get(EmailCredential, actor.id)
            hashed = credential.password_hash if credential else None
        if hashed is None:
            return
        # Same per-client and per-account limits as signing in with a password.
        self.email._limits("login", client, email_key(actor.email), now)
        if not password or len(password) > 128 or not verify_password(hashed, password):
            raise AccountDeletionError("Password is incorrect")

    def _remove(self, keys: set[str]) -> int:
        if not keys:
            return 0
        if self.storage is None:
            raise AccountDeletionError(
                "File storage is not configured; nothing was deleted", 503
            )
        for key in sorted(keys):
            self.storage.delete(key)
        return len(keys)

    def delete(
        self,
        actor: Account,
        *,
        email: str,
        password: str | None,
        client: str,
        now: int,
    ) -> DeletionResult:
        self._confirm(actor, email, password, client=client, now=now)
        # Act for the account throughout, so row-level security is a second lock.
        with account_scope(actor.id):
            with Session(self.engine) as db:
                first = _stored_keys(db, actor.id)
            try:
                removed = self._remove(first)
            except StorageError:
                raise AccountDeletionError(
                    "Could not delete stored files; nothing else was deleted. "
                    "Try again.",
                    503,
                ) from None
            rows = 0
            with Session(self.engine) as db:
                begin_serialized(db)
                later = _stored_keys(db, actor.id) - first
                for table in deletion_order(db):
                    result = db.execute(
                        text(f'DELETE FROM "{table}" WHERE user_id = :owner'),
                        {"owner": actor.id},
                    )
                    rows += int(getattr(result, "rowcount", 0) or 0)
                result = db.execute(
                    text("DELETE FROM users WHERE id = :owner"), {"owner": actor.id}
                )
                rows += int(getattr(result, "rowcount", 0) or 0)
                db.commit()
            try:
                removed += self._remove(later)
            except (StorageError, AccountDeletionError):
                # The rows are gone; never report content or keys in logs.
                logger.warning("Some files added during account deletion remain")
        return DeletionResult(rows=rows, files=removed)
