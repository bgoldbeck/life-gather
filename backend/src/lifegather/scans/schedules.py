"""Owned calendar schedules enqueue registered handlers through the shared runner."""

import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifegather.auth.models import User
from lifegather.auth.store import Account
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError, fingerprint
from lifegather.scans.models import ScanSchedule
from lifegather.scans.recurrence import latest_occurrence, next_occurrence, zone
from lifegather.scans.service import ScanBusy, ScanService


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str = Field(min_length=1, max_length=100)
    handler_key: str = Field(min_length=1, max_length=50)
    config: dict[str, Any]
    timezone: str = Field(min_length=1, max_length=100)
    cadence: Literal["daily", "weekly"]
    weekday: int = Field(default=0, ge=0, le=6)
    local_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    lookback_days: int = Field(ge=1, le=30)
    request_id: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        zone(value)
        return value

    @field_validator("label", "request_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A label and request identity are required")
        return value


class ScheduleService:
    def __init__(self, scans: ScanService) -> None:
        self.scans = scans

    @staticmethod
    def owned(db: Session, actor: Account, identifier: str) -> ScanSchedule:
        row = db.scalar(
            select(ScanSchedule).where(
                ScanSchedule.user_id == actor.id, ScanSchedule.id == identifier
            )
        )
        if row is None:
            raise MemoryError("Schedule not found")
        return row

    @staticmethod
    def view(row: ScanSchedule) -> dict[str, Any]:
        keys = (
            "id",
            "label",
            "handler_key",
            "timezone",
            "cadence",
            "weekday",
            "local_time",
            "lookback_days",
            "enabled",
            "revision",
            "next_run",
            "last_due",
            "last_run_id",
            "last_status",
            "created_at",
            "updated_at",
        )
        return {
            **{key: getattr(row, key) for key in keys},
            "scope": json.loads(row.config_json),
        }

    def list(self, actor: Account) -> dict[str, Any]:
        with Session(self.scans.engine) as db:
            rows = db.scalars(
                select(ScanSchedule)
                .where(ScanSchedule.user_id == actor.id)
                .order_by(ScanSchedule.created_at, ScanSchedule.id)
                .limit(5)
            )
            return {"items": [self.view(row) for row in rows]}

    def snapshot(
        self, actor: Account, key: str, config: dict[str, Any], lookback: int
    ) -> dict[str, Any]:
        handler = self.scans.registry.get(key)
        now = self.scans.clock()
        value = handler.window(config, max(0, now - lookback * 86400), now)
        normalized = self.scans.registry.normalize(key, value)
        prepared = handler.prepare(actor, normalized)
        if len(json.dumps(prepared.config).encode()) > 16384:
            raise MemoryError("Schedule configuration exceeds supported limits")
        return prepared.config

    def create(self, actor: Account, data: ScheduleInput) -> dict[str, Any]:
        data = ScheduleInput.model_validate(data)
        signature = fingerprint(data.model_dump(mode="json"))
        with self.scans.memory._write() as db:
            existing = db.scalar(
                select(ScanSchedule).where(
                    ScanSchedule.user_id == actor.id,
                    ScanSchedule.request_id == data.request_id,
                )
            )
            if existing:
                if signature != existing.fingerprint:
                    raise NoteConflict("Schedule request conflict")
                return self.view(existing)
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(ScanSchedule)
                    .where(ScanSchedule.user_id == actor.id)
                )
                or 0
            )
            if count >= 5:
                raise MemoryError(
                    "Schedule limit reached (five per user); edit an existing schedule"
                )
            config = self.snapshot(
                actor, data.handler_key, data.config, data.lookback_days
            )
            now = self.scans.clock()
            row = ScanSchedule(
                id=str(uuid4()),
                user_id=actor.id,
                request_id=data.request_id,
                fingerprint=signature,
                label=data.label,
                handler_key=data.handler_key,
                config_json=json.dumps(config),
                timezone=data.timezone,
                cadence=data.cadence,
                weekday=data.weekday,
                local_time=data.local_time,
                lookback_days=data.lookback_days,
                enabled=True,
                revision=1,
                next_run=next_occurrence(
                    now, data.timezone, data.cadence, data.weekday, data.local_time
                ),
                last_due=None,
                last_run_id=None,
                last_status="scheduled",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            self.scans.memory._audit(
                db, actor, "scan_schedule_created", row.id, now * 1000000
            )
            return self.view(row)

    def edit(
        self, actor: Account, identifier: str, revision: int, data: ScheduleInput
    ) -> dict[str, Any]:
        data = ScheduleInput.model_validate(data)
        with self.scans.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.revision != revision:
                raise NoteConflict("Schedule changed; refresh before editing")
            config = self.snapshot(
                actor, data.handler_key, data.config, data.lookback_days
            )
            for key in (
                "label",
                "handler_key",
                "timezone",
                "cadence",
                "weekday",
                "local_time",
                "lookback_days",
            ):
                setattr(row, key, getattr(data, key))
            row.config_json = json.dumps(config)
            row.revision += 1
            row.updated_at = self.scans.clock()
            row.next_run = next_occurrence(
                row.updated_at, row.timezone, row.cadence, row.weekday, row.local_time
            )
            row.last_status = "scheduled" if row.enabled else "paused"
            self.scans.memory._audit(
                db, actor, "scan_schedule_edited", row.id, row.updated_at * 1000000
            )
            return self.view(row)

    def toggle(
        self, actor: Account, identifier: str, revision: int, enabled: bool
    ) -> dict[str, Any]:
        with self.scans.memory._write() as db:
            row = self.owned(db, actor, identifier)
            if row.revision != revision:
                raise NoteConflict("Schedule changed; refresh before updating")
            if row.enabled == enabled:
                return self.view(row)
            if enabled:
                config = self.snapshot(
                    actor,
                    row.handler_key,
                    json.loads(row.config_json),
                    row.lookback_days,
                )
                row.config_json = json.dumps(config)
                row.next_run = next_occurrence(
                    self.scans.clock(),
                    row.timezone,
                    row.cadence,
                    row.weekday,
                    row.local_time,
                )
            row.enabled = enabled
            row.revision += 1
            row.updated_at = self.scans.clock()
            row.last_status = "scheduled" if enabled else "paused"
            self.scans.memory._audit(
                db,
                actor,
                "scan_schedule_resumed" if enabled else "scan_schedule_paused",
                row.id,
                row.updated_at * 1000000,
            )
            return self.view(row)

    def dispatch(self) -> int:
        now = self.scans.clock()
        with self.scans.memory._write() as db:
            rows = list(
                db.scalars(
                    select(ScanSchedule)
                    .where(ScanSchedule.enabled.is_(True), ScanSchedule.next_run <= now)
                    .order_by(ScanSchedule.next_run, ScanSchedule.id)
                    .limit(20)
                )
            )
            for row in rows:
                user = db.get(User, row.user_id)
                if user is None:
                    continue
                actor = Account(user.id, user.email, user.name)
                due = max(
                    row.next_run,
                    latest_occurrence(
                        now, row.timezone, row.cadence, row.weekday, row.local_time
                    ),
                )
                snapshot = json.loads(row.config_json)
                try:
                    handler = self.scans.registry.get(row.handler_key)
                    handler.authorize(db, actor, snapshot)
                    config = handler.window(
                        snapshot, max(0, due - row.lookback_days * 86400), due
                    )
                    run = self.scans.enqueue_in(
                        db,
                        actor,
                        row.handler_key,
                        config,
                        f"schedule:{row.id}:{row.revision}:{due}",
                    )
                    row.last_run_id = run["id"]
                    row.last_status = "queued"
                except ScanBusy:
                    row.last_status = "skipped_overlap"
                except MemoryError:
                    row.enabled = False
                    row.revision += 1
                    row.last_status = "blocked"
                row.last_due = due
                row.updated_at = now
                row.next_run = next_occurrence(
                    now, row.timezone, row.cadence, row.weekday, row.local_time
                )
                self.scans.memory._audit(
                    db, actor, "scan_schedule_" + row.last_status, row.id, now * 1000000
                )
            return len(rows)
