"""Durable scan lifecycle, leases, owner scope and atomic evidence checkpoints."""

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.models import User
from lifegather.auth.store import Account
from lifegather.memory.history import event_origin
from lifegather.memory.models import Episode
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, MemoryService, fingerprint
from lifegather.scans.models import ScanRun, ScanRunItem
from lifegather.scans.registry import ScanBatch, ScanProcessor, ScanRegistry


class LeaseLost(Exception):
    pass


class ScanCanceled(Exception):
    pass


class ScanBusy(NoteConflict):
    pass


@dataclass(frozen=True)
class ScanClaim:
    id: str
    actor: Account
    handler_key: str
    token: str
    config: dict[str, Any]
    cursor: dict[str, Any]


class ScanService:
    def __init__(
        self,
        engine: Engine,
        registry: ScanRegistry,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.engine, self.registry = engine, registry
        self.clock = clock or (lambda: int(time.time()))
        self.memory = MemoryService(engine)

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> ScanRun:
        row = db.scalar(
            select(ScanRun).where(
                ScanRun.user_id == actor.id,
                ScanRun.id == identifier,
            )
        )
        if row is None:
            raise MemoryError("Scan not found")
        return row

    @staticmethod
    def view(row: ScanRun) -> dict[str, Any]:
        fields = (
            "id",
            "handler_key",
            "state",
            "cancel_requested",
            "scanned",
            "imported",
            "existing",
            "skipped",
            "attempts",
            "truncated",
            "error",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        )
        return {
            **{key: getattr(row, key) for key in fields},
            "scope": json.loads(row.config_json),
        }

    def list(self, actor: Account, cursor: str = "") -> dict[str, Any]:
        with Session(self.engine) as db:
            query = select(ScanRun).where(ScanRun.user_id == actor.id)
            if cursor:
                previous = self.owned(db, actor, cursor)
                query = query.where(
                    or_(
                        ScanRun.created_at < previous.created_at,
                        and_(
                            ScanRun.created_at == previous.created_at,
                            ScanRun.id < previous.id,
                        ),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(
                        ScanRun.created_at.desc(),
                        ScanRun.id.desc(),
                    ).limit(21)
                )
            )
            return {
                "items": [self.view(row) for row in rows[:20]],
                "next_cursor": rows[19].id if len(rows) > 20 else None,
            }

    def get(self, actor: Account, identifier: str, after: int = 0) -> dict[str, Any]:
        if not 0 <= after <= 50:
            raise MemoryError("Invalid scan result cursor")
        with Session(self.engine) as db:
            row = self.owned(db, actor, identifier)
            items = list(
                db.scalars(
                    select(ScanRunItem)
                    .where(
                        ScanRunItem.user_id == actor.id,
                        ScanRunItem.run_id == row.id,
                        ScanRunItem.sequence > after,
                    )
                    .order_by(ScanRunItem.sequence)
                    .limit(11)
                )
            )
            return {
                **self.view(row),
                "items": [
                    {
                        "sequence": i.sequence,
                        "source_id": i.source_id,
                        "label": i.label,
                        "state": i.state,
                        "reason": i.reason,
                        "metadata": json.loads(i.metadata_json),
                    }
                    for i in items[:10]
                ],
                "next_after": items[9].sequence if len(items) > 10 else None,
            }

    def enqueue(
        self,
        actor: Account,
        handler_key: str,
        config: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        with self.memory._write() as db:
            return self.enqueue_in(db, actor, handler_key, config, request_id)

    def enqueue_in(
        self,
        db: Session,
        actor: Account,
        handler_key: str,
        config: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        if not request_id.strip() or len(request_id) > 100:
            raise MemoryError("Choose a stable scan request identity")
        normalized = self.registry.normalize(handler_key, config)
        signature = fingerprint([handler_key, normalized.model_dump(mode="json")])
        old = db.scalar(
            select(ScanRun).where(
                ScanRun.user_id == actor.id,
                ScanRun.request_id == request_id,
            )
        )
        if old:
            if old.fingerprint != signature:
                raise NoteConflict("Scan request conflict")
            return self.view(old)
        prepared = self.registry.get(handler_key).prepare(actor, normalized)
        serialized = json.dumps(prepared.config, sort_keys=True)
        if (
            not prepared.resource_key
            or len(prepared.resource_key) > 150
            or len(serialized.encode()) > 16384
        ):
            raise MemoryError("Scan configuration exceeds the supported limits")
        active = db.scalar(
            select(ScanRun.id)
            .where(
                ScanRun.user_id == actor.id,
                ScanRun.resource_key == prepared.resource_key,
                ScanRun.state.in_(["queued", "running"]),
            )
            .limit(1)
        )
        if active:
            raise ScanBusy("A scan is already queued or running for this connection")
        count = (
            db.scalar(
                select(func.count())
                .select_from(ScanRun)
                .where(
                    ScanRun.user_id == actor.id,
                    ScanRun.created_at > self.clock() - 86400,
                )
            )
            or 0
        )
        if count >= 20:
            raise MemoryError("Daily scan limit reached (20 runs per user)")
        now = self.clock()
        row = ScanRun(
            id=str(uuid4()),
            user_id=actor.id,
            handler_key=handler_key,
            resource_key=prepared.resource_key,
            config_json=serialized,
            cursor_json="{}",
            request_id=request_id,
            fingerprint=signature,
            state="queued",
            cancel_requested=False,
            scanned=0,
            imported=0,
            existing=0,
            skipped=0,
            steps=0,
            attempts=0,
            truncated=False,
            error=None,
            lease_token=None,
            lease_until=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        db.add(row)
        db.flush()
        self.memory._audit(db, actor, "scan_requested", row.id, now * 1000000)
        return self.view(row)

    def cancel(self, actor: Account, identifier: str) -> dict[str, Any]:
        with self.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.state in {"queued", "running"} and not row.cancel_requested:
                row.cancel_requested = True
                row.updated_at = self.clock()
                if row.state == "queued":
                    row.state = "canceled"
                    row.completed_at = row.updated_at
                self.memory._audit(
                    db, actor, "scan_cancel_requested", row.id, row.updated_at * 1000000
                )
            return self.view(row)

    def origin_for(self, claim: ScanClaim) -> dict[str, Any]:
        with Session(self.engine) as db:
            self.owned(db, claim.actor, claim.id)
            origin = event_origin(db, claim.actor, claim.id, ("scan_requested",)) or {}
            return {
                **origin,
                "interface": "worker",
                "method": "import",
                "related_id": claim.id,
            }

    def claim(self) -> ScanClaim | None:
        with self.memory._write() as db:
            now = self.clock()
            row = db.scalar(
                select(ScanRun)
                .where(
                    or_(
                        ScanRun.state == "queued",
                        and_(ScanRun.state == "running", ScanRun.lease_until <= now),
                    )
                )
                .order_by(ScanRun.created_at, ScanRun.id)
                .limit(1)
            )
            if row is None:
                return None
            if row.cancel_requested or row.attempts >= 3:
                row.state = "canceled" if row.cancel_requested else "failed"
                row.error = (
                    None
                    if row.cancel_requested
                    else "Scan recovery limit reached. Request a new scan."
                )
                row.completed_at = row.updated_at = now
                row.lease_token = None
                row.lease_until = None
                return None
            user = db.get(User, row.user_id)
            if user is None:
                raise MemoryError("Scan owner is unavailable")
            row.state = "running"
            row.lease_token = secrets.token_urlsafe(32)
            row.lease_until = now + 60
            row.started_at = row.started_at if row.started_at is not None else now
            row.updated_at = now
            row.attempts += 1
            return ScanClaim(
                row.id,
                Account(user.id, user.email, user.name),
                row.handler_key,
                row.lease_token,
                json.loads(row.config_json),
                json.loads(row.cursor_json),
            )

    def claimed(self, db: Session, identifier: str, token: str) -> ScanRun:
        row = db.get(ScanRun, identifier)
        if (
            row is None
            or row.state != "running"
            or row.lease_token != token
            or (row.lease_until or 0) <= self.clock()
        ):
            raise LeaseLost()
        if row.cancel_requested:
            raise ScanCanceled()
        return row

    def heartbeat(self, identifier: str, token: str) -> None:
        with self.memory._write() as db:
            row = self.claimed(db, identifier, token)
            row.lease_until = self.clock() + 60

    def commit_batch(self, claim: ScanClaim, batch: ScanBatch) -> None:
        cursor = json.dumps(batch.next_cursor or {}, sort_keys=True)
        if len(batch.items) > 1 or len(cursor.encode()) > 16384:
            raise MemoryError("Scan checkpoint exceeds supported limits")
        with self.memory._write() as db:
            row = self.claimed(db, claim.id, claim.token)
            self.registry.get(claim.handler_key).authorize(
                db, claim.actor, claim.config
            )
            if row.user_id != claim.actor.id or row.steps >= 100:
                raise MemoryError("Scan work limit reached")
            if (
                not batch.items
                and batch.next_cursor is not None
                and cursor == row.cursor_json
            ):
                raise MemoryError("Scan made no progress")
            for item in batch.items:
                metadata = json.dumps(item.metadata)
                if (
                    not item.key
                    or len(item.key) > 200
                    or len(item.label) > 200
                    or len(item.reason) > 200
                    or len(metadata.encode()) > 4096
                ):
                    raise MemoryError("Scan item exceeds supported limits")
                if db.scalar(
                    select(ScanRunItem.id).where(
                        ScanRunItem.user_id == claim.actor.id,
                        ScanRunItem.run_id == row.id,
                        ScanRunItem.item_key == item.key,
                    )
                ):
                    continue
                if row.scanned >= 50:
                    raise MemoryError("Scan message limit reached")
                source_id = None
                state = "skipped"
                if item.source is not None:
                    exists = (
                        db.scalar(
                            select(Episode.id)
                            .where(
                                Episode.user_id == claim.actor.id,
                                Episode.namespace == item.source.namespace,
                                Episode.external_id == item.source.external_id,
                            )
                            .limit(1)
                        )
                        if item.source.external_id is not None
                        else None
                    )
                    source = self.memory._ingest_in(db, claim.actor, item.source)
                    source_id = source.id
                    state = "existing" if exists else "saved"
                    processor = self.registry.get(claim.handler_key)
                    if isinstance(processor, ScanProcessor):
                        derived = processor.commit_in(
                            db, claim.actor, claim.config, source_id, item
                        )
                        metadata = json.dumps({**item.metadata, **derived})
                        if len(metadata.encode()) > 4096:
                            raise MemoryError("Scan result exceeds supported limits")
                row.scanned += 1
                row.imported += int(state == "saved")
                row.existing += int(state == "existing")
                row.skipped += int(state == "skipped")
                db.add(
                    ScanRunItem(
                        id=str(uuid4()),
                        user_id=claim.actor.id,
                        run_id=row.id,
                        sequence=row.scanned,
                        item_key=item.key,
                        source_id=source_id,
                        label=item.label,
                        state=state,
                        reason=item.reason,
                        metadata_json=metadata,
                    )
                )
            row.steps += 1
            row.cursor_json = cursor
            row.truncated = row.truncated or batch.truncated
            row.updated_at = self.clock()
            if batch.next_cursor is None:
                row.state = "completed"
                row.completed_at = row.updated_at
                row.lease_token = None
                row.lease_until = None
                self.memory._audit(
                    db, claim.actor, "scan_completed", row.id, row.updated_at * 1000000
                )
            else:
                row.lease_until = self.clock() + 60

    def finish(self, claim: ScanClaim, state: str, error: str | None = None) -> None:
        if state not in {"failed", "canceled"}:
            raise ValueError("Invalid scan completion state")
        with self.memory._write() as db:
            row = db.get(ScanRun, claim.id)
            if (
                row is None
                or row.state != "running"
                or row.lease_token != claim.token
                or (row.lease_until or 0) <= self.clock()
            ):
                return
            row.state = "canceled" if row.cancel_requested else state
            row.error = None if row.state == "canceled" else error
            row.completed_at = row.updated_at = self.clock()
            row.lease_token = None
            row.lease_until = None

    def release(self, claim: ScanClaim, *, orderly: bool = False) -> None:
        with self.memory._write() as db:
            row = db.get(ScanRun, claim.id)
            if row and row.state == "running" and row.lease_token == claim.token:
                row.state = "canceled" if row.cancel_requested else "queued"
                row.completed_at = self.clock() if row.cancel_requested else None
                row.lease_token = None
                row.lease_until = None
                if orderly:
                    # A planned hand-back is not a crash; keep the recovery budget.
                    row.attempts = max(row.attempts - 1, 0)
                    row.updated_at = self.clock()

    def pause(self, claim: ScanClaim) -> None:
        """Queue a checkpointed run again at a tick's time limit."""
        self.release(claim, orderly=True)
