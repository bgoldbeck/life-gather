"""Deleted account ids, kept only until installation backups holding them expire.

A system table: it has no owner column, and the per-account database role has
no access to it (migration 0039). An entry holds the deleted account's random
id and two times, never an email, name or content. It lets the operator know
when the last backup copy is gone, and lets a restore of an older backup erase
accounts that were deleted after that backup was made.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from lifegather.auth.models import Base
from lifegather.database import account_scope

DAY_SECONDS = 86_400
LEDGER_FORMAT: Final = "lifegather-deleted-accounts/1"
MAX_LEDGER_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 100_000

logger = logging.getLogger(__name__)


class DeletedAccount(Base):
    __tablename__ = "deleted_accounts"
    account_id: Mapped[str] = mapped_column(primary_key=True)
    deleted_at: Mapped[int]
    backups_expire_at: Mapped[int] = mapped_column(index=True)


class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    account_id: str = Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    deleted_at: int = Field(ge=0)
    backups_expire_at: int = Field(ge=0)


class LedgerFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    format: Literal["lifegather-deleted-accounts/1"] = LEDGER_FORMAT
    entries: list[LedgerEntry] = Field(max_length=MAX_ENTRIES)


def record_deletion(
    engine: Engine, account_id: str, *, now: int, retention_days: int
) -> int:
    """Remember one deletion; returns when the last backup copy expires."""
    expires = now + retention_days * DAY_SECONDS
    with account_scope(None), Session(engine) as db:
        db.execute(
            insert(DeletedAccount)
            .values(account_id=account_id, deleted_at=now, backups_expire_at=expires)
            .on_conflict_do_nothing(index_elements=["account_id"])
        )
        db.commit()
    return expires


def purge_expired(engine: Engine, *, now: int) -> int:
    """Forget deletions whose backup copies have all expired."""
    with account_scope(None), Session(engine) as db:
        result = db.execute(
            delete(DeletedAccount).where(DeletedAccount.backups_expire_at <= now)
        )
        db.commit()
        return int(getattr(result, "rowcount", 0) or 0)


def ledger_entries(engine: Engine) -> list[LedgerEntry]:
    with account_scope(None), Session(engine) as db:
        rows = db.scalars(
            select(DeletedAccount)
            .order_by(DeletedAccount.deleted_at)
            .limit(MAX_ENTRIES)
        )
        return [
            LedgerEntry(
                account_id=row.account_id,
                deleted_at=row.deleted_at,
                backups_expire_at=row.backups_expire_at,
            )
            for row in rows
        ]


def write_ledger(path: Path, entries: list[LedgerEntry]) -> None:
    """Write a new private ledger file; never overwrites an existing path."""
    raw = LedgerFile(entries=entries).model_dump_json().encode("utf-8")
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def read_ledger(path: Path) -> list[LedgerEntry]:
    with path.open("rb") as source:
        raw = source.read(MAX_LEDGER_BYTES + 1)
    if len(raw) > MAX_LEDGER_BYTES:
        raise ValueError("The deleted-accounts file is too large")
    return LedgerFile.model_validate(json.loads(raw)).entries


async def ledger_sweeps(engine: Engine, interval: float = 3600) -> None:
    """Forget expired deletions on startup and then hourly until cancelled."""
    while True:
        try:
            await asyncio.to_thread(purge_expired, engine, now=int(time.time()))
        except Exception:
            logger.exception("Deleted-account ledger sweep failed")
        await asyncio.sleep(interval)
