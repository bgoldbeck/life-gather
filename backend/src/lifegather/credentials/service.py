import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.credentials.models import Credential, UserSettings, VaultKey
from lifegather.database import begin_serialized

if TYPE_CHECKING:
    from lifegather.config import Settings

KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


AUTH_RECHECK_SECONDS = 3600


class ReconnectRequired(Exception):
    """A provider refused a saved credential as expired or revoked.

    The message is fixed, safe text: it never carries provider response content.
    """

    def __init__(
        self, kind: Literal["ai", "gmail"], identifier: str, provider: str
    ) -> None:
        self.kind, self.identifier, self.provider = kind, identifier, provider
        super().__init__(
            "Gmail access expired or was revoked. Reconnect Gmail to continue."
            if kind == "gmail"
            else "The AI provider refused the saved key; it may have expired or "
            "been revoked. Reconnect it with a new key in Settings."
        )

    def view(self) -> dict[str, str]:
        key = "mailbox_id" if self.kind == "gmail" else "credential_id"
        return {"kind": self.kind, key: self.identifier, "provider": self.provider}


class VaultError(ValueError):
    def __init__(self, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.status = status


class CredentialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ai", "email", "bank"]
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=100)
    secret: SecretStr = Field(min_length=1, max_length=8192)


@dataclass(frozen=True)
class CredentialMetadata:
    id: str
    kind: str
    provider: str
    label: str
    created_at: int
    updated_at: int
    auth_state: str | None = None
    auth_checked_at: int | None = None


class CredentialPage(TypedDict):
    items: list[dict[str, str | int]]
    next_cursor: str | None


def read_key(path: Path | None) -> bytes | None:
    if path is None:
        return None
    try:
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError("wrong key length")
        return key
    except (OSError, ValueError) as error:
        raise ValueError("Vault key must be a readable 32-byte key file") from error


def fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()


@dataclass(frozen=True)
class VaultKeyring:
    """Named vault keys; the first is active, the rest are previous keys."""

    keys: tuple[tuple[str, bytes], ...]

    @property
    def active(self) -> bytes:
        return self.keys[0][1]

    @property
    def active_id(self) -> str:
        return self.keys[0][0]

    def find(self, saved: str) -> tuple[str, bytes] | None:
        for key_id, key in self.keys:
            if secrets.compare_digest(fingerprint(key), saved):
                return key_id, key
        return None


def parse_keys(value: str) -> list[tuple[str, bytes]]:
    keys: list[tuple[str, bytes]] = []
    for entry in value.split(","):
        if not entry.strip():
            continue
        key_id, separator, encoded = entry.strip().partition(":")
        try:
            if not separator or not KEY_ID.fullmatch(key_id):
                raise ValueError
            key = base64.b64decode(encoded.strip(), validate=True)
        except (ValueError, binascii.Error):
            # Never echo the entry: it holds key material.
            raise ValueError(
                "LIFEGATHER_VAULT_KEYS entries must be id:base64 32-byte keys"
            ) from None
        if len(key) != 32:
            raise ValueError("LIFEGATHER_VAULT_KEYS keys must be 32 bytes")
        keys.append((key_id, key))
    return keys


def read_keyring(settings: "Settings") -> VaultKeyring | None:
    keys = parse_keys(settings.vault_keys.get_secret_value())
    file_key = read_key(settings.vault_key_file)
    if file_key is not None:
        # Alone, the file is the active key; beside env keys it is a previous one.
        keys.append(("file", file_key))
    if not keys:
        return None
    if len({key_id for key_id, _ in keys}) != len(keys) or len(
        {key for _, key in keys}
    ) != len(keys):
        raise ValueError("Vault key IDs and keys must be unique")
    return VaultKeyring(tuple(keys))


def credential_context(
    user_id: str, credential_id: str, kind: str, provider: str
) -> bytes:
    return json.dumps(
        ["lifegather-vault-v1", user_id, credential_id, kind, provider],
        separators=(",", ":"),
    ).encode()


def rotate_vault_key(engine: Engine, keyring: VaultKeyring) -> bool:
    """Re-encrypt every credential under the active key; True when rotated.

    Runs as a serialized writer, so credential saves and replacements wait for it;
    the fingerprint changes in the same transaction as the credential rewrite.
    """
    active = fingerprint(keyring.active)
    with Session(engine) as db, db.begin():
        begin_serialized(db)
        saved = db.scalar(select(VaultKey.fingerprint).where(VaultKey.id == 1))
        if saved is None or secrets.compare_digest(saved, active):
            return False
        previous = keyring.find(saved)
        if previous is None:
            raise VaultError("No configured vault key matches this database", 503)
        old, new = AESGCM(previous[1]), AESGCM(keyring.active)
        for row in db.scalars(select(Credential).order_by(Credential.id)):
            context = credential_context(row.user_id, row.id, row.kind, row.provider)
            try:
                secret = old.decrypt(row.nonce, row.ciphertext, context)
            except InvalidTag as error:
                raise VaultError("Credential cannot be decrypted", 503) from error
            row.nonce = os.urandom(12)
            row.ciphertext = new.encrypt(row.nonce, secret, context)
        db.execute(update(VaultKey).where(VaultKey.id == 1).values(fingerprint=active))
        return True


class PrivateSettings:
    def __init__(self, engine: Engine, key: bytes | None) -> None:
        self.engine = engine
        self.cipher = AESGCM(key) if key is not None else None
        self.fingerprint = fingerprint(key) if key is not None else None
        if self.fingerprint is not None:
            with Session(engine) as db, db.begin():
                db.execute(
                    insert(VaultKey)
                    .values(id=1, fingerprint=self.fingerprint)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                self._check_key(db)

    def _check_key(self, db: Session) -> None:
        # A rotation by another instance makes this instance's key stale; refuse
        # to write credentials that the database's current key could not read.
        # Without a recorded key nothing was encrypted yet (a configured key is
        # recorded at construction), so there is nothing a write could orphan.
        saved = db.scalar(select(VaultKey.fingerprint).where(VaultKey.id == 1))
        if saved is not None and (
            self.fingerprint is None
            or not secrets.compare_digest(saved, self.fingerprint)
        ):
            raise VaultError("Vault key does not match this database", 503)

    @property
    def enabled(self) -> bool:
        return self.cipher is not None

    def preferences(self, actor: Account) -> bool:
        with Session(self.engine) as db:
            value = db.scalar(
                select(UserSettings.allow_external_ai).where(
                    UserSettings.user_id == actor.id
                )
            )
            return bool(value)

    def set_preferences(self, actor: Account, allow_external_ai: bool) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                insert(UserSettings)
                .values(user_id=actor.id, allow_external_ai=allow_external_ai)
                .on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={"allow_external_ai": allow_external_ai},
                )
            )

    def theme(self, actor: Account) -> str:
        with Session(self.engine) as db:
            return (
                db.scalar(
                    select(UserSettings.theme).where(UserSettings.user_id == actor.id)
                )
                or "system"
            )

    def set_theme(self, actor: Account, theme: str) -> None:
        if theme not in {"system", "light", "dark", "forest-dark"}:
            raise VaultError("Invalid appearance", 422)
        with Session(self.engine) as db, db.begin():
            db.execute(
                insert(UserSettings)
                .values(user_id=actor.id, allow_external_ai=False, theme=theme)
                .on_conflict_do_update(
                    index_elements=["user_id"], set_={"theme": theme}
                )
            )

    @staticmethod
    def _metadata(row: Credential) -> CredentialMetadata:
        return CredentialMetadata(
            row.id,
            row.kind,
            row.provider,
            row.label,
            row.created_at,
            row.updated_at,
            row.auth_state,
            row.auth_checked_at,
        )

    @staticmethod
    def _context(actor: Account, row: Credential) -> bytes:
        return credential_context(actor.id, row.id, row.kind, row.provider)

    def _encrypt(self, actor: Account, row: Credential, secret: str) -> None:
        if self.cipher is None:
            raise VaultError("Credential storage is not configured", 503)
        if not secret.strip() or len(secret) > 8192:
            raise VaultError("Secret must contain 1 to 8192 characters", 422)
        row.nonce = os.urandom(12)
        row.ciphertext = self.cipher.encrypt(
            row.nonce, secret.encode(), self._context(actor, row)
        )

    @staticmethod
    def _owned(db: Session, actor: Account, credential_id: str) -> Credential:
        row = db.scalar(
            select(Credential)
            .where(Credential.user_id == actor.id, Credential.id == credential_id)
            .limit(1)
        )
        if row is None:
            raise VaultError("Credential not found")
        return row

    def list(self, actor: Account, cursor: str = "", limit: int = 25) -> CredentialPage:
        if not 1 <= limit <= 100:
            raise VaultError("Invalid page size", 422)
        with Session(self.engine) as db:
            rows = list(
                db.scalars(
                    select(Credential)
                    .where(
                        Credential.user_id == actor.id,
                        Credential.id > cursor,
                    )
                    .order_by(Credential.id)
                    .limit(limit + 1)
                )
            )
            items = [asdict(self._metadata(row)) for row in rows[:limit]]
            return {
                "items": items,
                "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
            }

    def save(
        self, actor: Account, kind: str, provider: str, label: str, secret: str
    ) -> CredentialMetadata:
        value = CredentialInput.model_validate(
            {
                "kind": kind,
                "provider": provider,
                "label": label,
                "secret": secret,
            }
        )
        now = int(time.time())
        row = Credential(
            id=str(uuid4()),
            user_id=actor.id,
            kind=value.kind,
            provider=value.provider,
            label=value.label,
            created_at=now,
            updated_at=now,
        )
        self._encrypt(actor, row, value.secret.get_secret_value())
        with Session(self.engine) as db:
            # Serialize the per-owner quota check and insert, including concurrent jobs.
            begin_serialized(db)
            count = db.scalar(
                select(func.count())
                .select_from(Credential)
                .where(Credential.user_id == actor.id)
            )
            if count is not None and count >= 100:
                raise VaultError("Credential limit reached", 409)
            self._check_key(db)
            db.add(row)
            db.flush()
            metadata = self._metadata(row)
            db.commit()
            return metadata

    def replace(
        self, actor: Account, credential_id: str, secret: str
    ) -> CredentialMetadata:
        with Session(self.engine) as db, db.begin():
            # Serialized with vault rotation so neither overwrites the other.
            begin_serialized(db)
            row = self._owned(db, actor, credential_id)
            self._check_key(db)
            self._encrypt(actor, row, secret)
            row.updated_at = int(time.time())
            # A new secret has not been tried yet.
            row.auth_state = row.auth_checked_at = None
            return self._metadata(row)

    def record_auth(
        self,
        actor: Account,
        credential_id: str,
        state: Literal["working", "reconnect"],
        read_at: int,
        now: int | None = None,
    ) -> None:
        """Record the provider's latest answer to an owned credential.

        `read_at` is when the caller read the secret it sent. A credential
        replaced or removed since then is left alone: the answer was about the
        old secret. Repeated successes are written at most hourly.
        """
        now = int(time.time()) if now is None else now
        with Session(self.engine) as db, db.begin():
            row = db.scalar(
                select(Credential)
                .where(Credential.user_id == actor.id, Credential.id == credential_id)
                .limit(1)
            )
            if (
                row is None
                or row.updated_at > read_at
                or (
                    state == "working"
                    and row.auth_state == "working"
                    and row.auth_checked_at is not None
                    and 0 <= now - row.auth_checked_at < AUTH_RECHECK_SECONDS
                )
            ):
                return
            row.auth_state, row.auth_checked_at = state, now

    def read_secret(self, actor: Account, credential_id: str) -> str:
        """Internal integration use only; deliberately absent from HTTP/MCP tools."""
        with Session(self.engine) as db:
            row = self._owned(db, actor, credential_id)
            if self.cipher is None:
                raise VaultError("Credential storage is not configured", 503)
            try:
                return self.cipher.decrypt(
                    row.nonce, row.ciphertext, self._context(actor, row)
                ).decode()
            except (InvalidTag, UnicodeDecodeError) as error:
                raise VaultError("Credential cannot be decrypted", 503) from error

    def remove(self, actor: Account, credential_id: str) -> None:
        with Session(self.engine) as db, db.begin():
            # Owner-scoped composite keys would otherwise block the SET NULL rule.
            for table in Credential.metadata.sorted_tables:
                for key in table.foreign_keys:
                    if key.column is Credential.__table__.c.id and (
                        key.ondelete == "SET NULL"
                    ):
                        db.execute(
                            update(table)
                            .where(
                                table.c.user_id == actor.id,
                                key.parent == credential_id,
                            )
                            .values({key.parent.name: None})
                        )
            result = db.execute(
                delete(Credential)
                .where(Credential.user_id == actor.id, Credential.id == credential_id)
                .returning(Credential.id)
            ).scalar()
            if result is None:
                raise VaultError("Credential not found")
