"""Explicit personal plans; no inferred maintenance or external side effects."""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import Field
from sqlalchemy import Engine, and_, case, or_, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import canonical_id, identity_group, member_ids
from lifegather.auth.store import Account
from lifegather.database import begin_snapshot
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.maintenance.schemas import (
    CalendarDate,
    Input,
    MaintenanceChange,
    MaintenanceCreate,
    MaintenanceFields,
    MaintenanceHistory,
    MaintenancePage,
)
from lifegather.memory.history import event_origin
from lifegather.memory.models import Entity
from lifegather.memory.notes import NoteConflict
from lifegather.memory.origins import change_origin
from lifegather.memory.schemas import SourceInput, SourceView
from lifegather.memory.service import MemoryError, MemoryService, fingerprint


class _Cursor(Input):
    scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    task_id: str = Field(min_length=1, max_length=36)
    revision_id: str = Field(min_length=1, max_length=36)
    due_on: CalendarDate


class MaintenanceService:
    def __init__(self, engine: Engine, clock: Callable[[], int] | None = None) -> None:
        self.engine = engine
        self.memory = MemoryService(engine, clock)

    def source_context(self, actor: Account, source_id: str) -> dict[str, Any] | None:
        """Describe this exact statement, separately from the current head.

        Only a real owner-bound revision FK grants typed task provenance. A
        caller-supplied source namespace or text cannot impersonate a task.
        """
        with Session(self.engine) as db:
            begin_snapshot(db)
            matches = list(
                db.scalars(
                    select(MaintenanceRevision)
                    .where(
                        MaintenanceRevision.user_id == actor.id,
                        MaintenanceRevision.source_id == source_id,
                    )
                    .limit(2)
                )
            )
            if len(matches) != 1:
                return None
            row = matches[0]
            task = self._task(db, actor, row.task_id)
            head = self._head(db, actor, task)
            target = self._target(db, actor, task.entity_id)
            return {
                "task_id": task.id,
                "entity_id": task.entity_id,
                "target": {"id": target.id, "name": target.name, "kind": target.kind},
                "revision_id": row.id,
                "source_id": row.source_id,
                "title": row.title,
                "due_on": row.due_on.isoformat() if row.due_on else None,
                "timezone": row.timezone,
                "state": row.state,
                "completed_on": row.completed_on.isoformat()
                if row.completed_on
                else None,
                "recorded_at": row.recorded_at,
                "superseded_at": row.superseded_at,
                "is_current_revision": row.id == head.id,
                "current_revision_id": head.id,
                "current_source_id": head.source_id,
                "read_at": max(self.memory.clock(), row.recorded_at, head.recorded_at),
            }

    @staticmethod
    def _task(db: Session, actor: Account, identifier: str) -> MaintenanceTask:
        row = db.scalar(
            select(MaintenanceTask).where(
                MaintenanceTask.user_id == actor.id, MaintenanceTask.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Maintenance task not found")
        return row

    @staticmethod
    def _head(
        db: Session, actor: Account, task: MaintenanceTask
    ) -> MaintenanceRevision:
        row = db.scalar(
            select(MaintenanceRevision).where(
                MaintenanceRevision.user_id == actor.id,
                MaintenanceRevision.task_id == task.id,
                MaintenanceRevision.superseded_at.is_(None),
            )
        )
        if row is None:
            raise MemoryError("Maintenance task has no current revision")
        return row

    def _target(self, db: Session, actor: Account, identifier: str) -> Entity:
        original = self.memory._entity(db, actor, identifier)
        if original.kind not in {"asset", "place"}:
            raise MemoryError("Maintenance requires an existing asset or place")
        return self.memory._entity(db, actor, canonical_id(db, actor, identifier))

    @staticmethod
    def _ack(row: MaintenanceRevision) -> dict[str, str]:
        return {"id": row.task_id, "revision_id": row.id}

    def _token(
        self,
        db: Session,
        actor: Account,
        task: MaintenanceTask,
        row: MaintenanceRevision,
    ) -> str:
        target = self._target(db, actor, task.entity_id)
        group = identity_group(db, actor, task.entity_id)
        return fingerprint(
            [
                actor.id,
                task.id,
                row.id,
                task.entity_id,
                target.id,
                target.name,
                group.id if group else None,
            ]
        )

    @staticmethod
    def _revision(
        db: Session, actor: Account, row: MaintenanceRevision
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "due_on": row.due_on.isoformat() if row.due_on else None,
            "timezone": row.timezone,
            "state": row.state,
            "completed_on": row.completed_on.isoformat() if row.completed_on else None,
            "source_id": row.source_id,
            "previous_id": row.previous_id,
            "recorded_at": row.recorded_at,
            "superseded_at": row.superseded_at,
            "origin": event_origin(
                db, actor, row.id, ("maintenance_created", "maintenance_revised")
            ),
        }

    def _view(
        self,
        db: Session,
        actor: Account,
        task: MaintenanceTask,
        row: MaintenanceRevision,
        now: int,
    ) -> dict[str, Any]:
        target = self._target(db, actor, task.entity_id)
        today = (
            datetime.fromtimestamp(now // 1_000_000, UTC)
            .astimezone(ZoneInfo(row.timezone))
            .date()
        )
        due_status = row.state
        if row.state == "open":
            due_status = (
                "unscheduled"
                if row.due_on is None
                else "overdue"
                if row.due_on < today
                else "today"
                if row.due_on == today
                else "upcoming"
            )
        return {
            "id": task.id,
            "entity_id": task.entity_id,
            "target": {"id": target.id, "name": target.name, "kind": target.kind},
            "revision": self._revision(db, actor, row),
            "state_token": self._token(db, actor, task, row),
            "due_status": due_status,
            "local_today": today.isoformat(),
        }

    def _source_in(
        self,
        db: Session,
        actor: Account,
        entity_id: str,
        data: MaintenanceFields,
    ) -> SourceView:
        record = self.memory._entity(db, actor, entity_id)
        structured = json.dumps(
            data.model_dump(
                mode="json",
                include={"title", "due_on", "timezone", "state", "completed_on"},
            ),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        # Structured fields are explicit manual inputs, not extracted/verified claims.
        return self.memory._ingest_in(
            db,
            actor,
            SourceInput(
                text=(
                    "Manual maintenance statement\n"
                    f"Original linked record: {record.name}\n"
                    f"Supplied task fields (user stated):\n{structured}\n"
                    f"Original statement:\n{data.text}"
                ),
                namespace="maintenance-revisions",
                external_id=data.request_id,
            ),
        )

    def _save_revision(
        self,
        db: Session,
        actor: Account,
        task: MaintenanceTask,
        data: MaintenanceFields,
        signature: str,
        previous: MaintenanceRevision | None,
        source: SourceView | None = None,
    ) -> MaintenanceRevision:
        source = source or self._source_in(db, actor, task.entity_id, data)
        now = max(
            self.memory.clock(),
            source.recorded_at,
            previous.recorded_at + 1 if previous else task.recorded_at,
        )
        if previous:
            previous.superseded_at = now
            db.flush()  # Release the partial unique current-head constraint first.
        row = MaintenanceRevision(
            id=str(uuid4()),
            user_id=actor.id,
            task_id=task.id,
            previous_id=previous.id if previous else None,
            title=data.title,
            due_on=data.due_on,
            timezone=data.timezone,
            state=data.state,
            completed_on=data.completed_on,
            source_id=source.id,
            request_id=data.request_id,
            fingerprint=signature,
            recorded_at=now,
            superseded_at=None,
        )
        db.add(row)
        db.flush()
        self.memory._audit(
            db,
            actor,
            "maintenance_revised" if previous else "maintenance_created",
            row.id,
            now,
        )
        return row

    def create(self, actor: Account, value: MaintenanceCreate) -> dict[str, str]:
        data = MaintenanceCreate.model_validate(value)
        signature = fingerprint(["create", data.model_dump(mode="json")])
        with change_origin(method="manual_entry"), self.memory._write() as db:
            existing = db.scalar(
                select(MaintenanceRevision).where(
                    MaintenanceRevision.user_id == actor.id,
                    MaintenanceRevision.request_id == data.request_id,
                )
            )
            if existing:
                if (
                    existing.fingerprint != signature
                    or existing.previous_id is not None
                ):
                    raise MemoryError("Maintenance request identity conflict")
                return self._ack(existing)
            self._target(db, actor, data.entity_id)
            identifier = str(uuid4())
            source = self._source_in(db, actor, data.entity_id, data)
            task = MaintenanceTask(
                id=identifier,
                user_id=actor.id,
                entity_id=data.entity_id,
                source_id=source.id,
                request_id=data.request_id,
                fingerprint=signature,
                recorded_at=source.recorded_at,
            )
            db.add(task)
            db.flush()
            return self._ack(
                self._save_revision(db, actor, task, data, signature, None, source)
            )

    def revise(self, actor: Account, value: MaintenanceChange) -> dict[str, str]:
        data = MaintenanceChange.model_validate(value)
        signature = fingerprint(["revise", data.model_dump(mode="json")])
        with change_origin(method="correction"), self.memory._write() as db:
            task = self._task(db, actor, data.task_id)
            existing = db.scalar(
                select(MaintenanceRevision).where(
                    MaintenanceRevision.user_id == actor.id,
                    MaintenanceRevision.request_id == data.request_id,
                )
            )
            if existing:
                if existing.task_id != task.id or existing.fingerprint != signature:
                    raise MemoryError("Maintenance request identity conflict")
                return self._ack(existing)
            previous = self._head(db, actor, task)
            if self._token(db, actor, task, previous) != data.state_token:
                raise NoteConflict(
                    "Maintenance task changed. Reload it before editing again."
                )
            return self._ack(
                self._save_revision(db, actor, task, data, signature, previous)
            )

    def get(self, actor: Account, identifier: str) -> dict[str, Any]:
        with Session(self.engine) as db:
            begin_snapshot(db)
            task = self._task(db, actor, identifier)
            return self._view(
                db, actor, task, self._head(db, actor, task), self.memory.clock()
            )

    def list(self, actor: Account, value: MaintenancePage) -> dict[str, Any]:
        data = MaintenancePage.model_validate(value)
        with Session(self.engine) as db:
            begin_snapshot(db)
            identifiers = None
            if data.entity_id:
                self._target(db, actor, data.entity_id)
                identifiers = member_ids(db, actor, data.entity_id)
            scope = fingerprint(
                [actor.id, sorted(identifiers) if identifiers else None, data.state]
            )
            query = (
                select(MaintenanceTask, MaintenanceRevision)
                .join(
                    MaintenanceRevision,
                    and_(
                        MaintenanceRevision.user_id == MaintenanceTask.user_id,
                        MaintenanceRevision.task_id == MaintenanceTask.id,
                    ),
                )
                .where(
                    MaintenanceTask.user_id == actor.id,
                    MaintenanceRevision.user_id == actor.id,
                    MaintenanceRevision.superseded_at.is_(None),
                )
            )
            if identifiers:
                query = query.where(MaintenanceTask.entity_id.in_(identifiers))
            if data.state != "all":
                query = query.where(MaintenanceRevision.state == data.state)
            if data.cursor:
                try:
                    raw = base64.b64decode(
                        data.cursor + "=" * (-len(data.cursor) % 4),
                        altchars=b"-_",
                        validate=True,
                    )
                    cursor = _Cursor.model_validate_json(raw)
                except ValueError:
                    raise MemoryError("Invalid maintenance cursor") from None
                anchor = self._task(db, actor, cursor.task_id)
                head = self._head(db, actor, anchor)
                if (
                    cursor.scope != scope
                    or (identifiers and anchor.entity_id not in identifiers)
                    or (data.state != "all" and head.state != data.state)
                ):
                    raise MemoryError("Choose a maintenance cursor from this list")
                if head.id != cursor.revision_id or head.due_on != cursor.due_on:
                    raise NoteConflict("Maintenance task changed. Refresh this list.")
                if cursor.due_on is None:
                    query = query.where(
                        MaintenanceRevision.due_on.is_(None),
                        MaintenanceTask.id > cursor.task_id,
                    )
                else:
                    query = query.where(
                        or_(
                            MaintenanceRevision.due_on > cursor.due_on,
                            and_(
                                MaintenanceRevision.due_on == cursor.due_on,
                                MaintenanceTask.id > cursor.task_id,
                            ),
                            MaintenanceRevision.due_on.is_(None),
                        )
                    )
            rows = list(
                db.execute(
                    query.order_by(
                        case((MaintenanceRevision.due_on.is_(None), 1), else_=0),
                        MaintenanceRevision.due_on,
                        MaintenanceTask.id,
                    ).limit(data.limit + 1)
                )
            )
            now = self.memory.clock()
            following = None
            if len(rows) > data.limit:
                task, revision = rows[data.limit - 1]
                cursor = _Cursor(
                    scope=scope,
                    task_id=task.id,
                    revision_id=revision.id,
                    due_on=revision.due_on,
                )
                following = (
                    base64.urlsafe_b64encode(cursor.model_dump_json().encode())
                    .decode()
                    .rstrip("=")
                )
            return {
                "items": [
                    self._view(db, actor, task, row, now)
                    for task, row in rows[: data.limit]
                ],
                "next_cursor": following,
            }

    def history(self, actor: Account, value: MaintenanceHistory) -> dict[str, Any]:
        data = MaintenanceHistory.model_validate(value)
        with Session(self.engine) as db:
            begin_snapshot(db)
            self._task(db, actor, data.task_id)
            query = select(MaintenanceRevision).where(
                MaintenanceRevision.user_id == actor.id,
                MaintenanceRevision.task_id == data.task_id,
            )
            if data.cursor:
                anchor = db.scalar(query.where(MaintenanceRevision.id == data.cursor))
                if anchor is None:
                    raise MemoryError(
                        "Choose a history cursor from this maintenance task"
                    )
                query = query.where(
                    or_(
                        MaintenanceRevision.recorded_at > anchor.recorded_at,
                        and_(
                            MaintenanceRevision.recorded_at == anchor.recorded_at,
                            MaintenanceRevision.id > anchor.id,
                        ),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(
                        MaintenanceRevision.recorded_at, MaintenanceRevision.id
                    ).limit(data.limit + 1)
                )
            )
            return {
                "items": [self._revision(db, actor, row) for row in rows[: data.limit]],
                "next_cursor": rows[data.limit - 1].id
                if len(rows) > data.limit
                else None,
            }
