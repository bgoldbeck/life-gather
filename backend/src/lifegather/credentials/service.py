import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypedDict
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.credentials.models import Credential, UserSettings, VaultKey


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


class PrivateSettings:
    def __init__(self, engine: Engine, key: bytes | None) -> None:
        self.engine = engine
        self.cipher = AESGCM(key) if key is not None else None
        if key is not None:
            fingerprint = hashlib.sha256(key).hexdigest()
            with Session(engine) as db, db.begin():
                db.execute(
                    insert(VaultKey)
                    .values(id=1, fingerprint=fingerprint)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
                saved = db.scalar(select(VaultKey.fingerprint).where(VaultKey.id == 1))
                if saved is None or not secrets.compare_digest(saved, fingerprint):
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

    @staticmethod
    def _metadata(row: Credential) -> CredentialMetadata:
        return CredentialMetadata(
            row.id, row.kind, row.provider, row.label, row.created_at, row.updated_at
        )

    @staticmethod
    def _context(actor: Account, row: Credential) -> bytes:
        return json.dumps(
            ["lifegather-vault-v1", actor.id, row.id, row.kind, row.provider],
            separators=(",", ":"),
        ).encode()

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
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            count = db.scalar(
                select(func.count())
                .select_from(Credential)
                .where(Credential.user_id == actor.id)
            )
            if count is not None and count >= 100:
                raise VaultError("Credential limit reached", 409)
            db.add(row)
            db.flush()
            metadata = self._metadata(row)
            db.commit()
            return metadata

    def replace(
        self, actor: Account, credential_id: str, secret: str
    ) -> CredentialMetadata:
        with Session(self.engine) as db, db.begin():
            row = self._owned(db, actor, credential_id)
            self._encrypt(actor, row, secret)
            row.updated_at = int(time.time())
            return self._metadata(row)

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
            result = db.execute(
                delete(Credential)
                .where(Credential.user_id == actor.id, Credential.id == credential_id)
                .returning(Credential.id)
            ).scalar()
            if result is None:
                raise VaultError("Credential not found")
