"""Installation-wide operator overview: counts only, never personal content.

Reads every account's rows, so callers must already have checked that the
signed-in account is an operator. Runs in the trusted system context.
"""

import hashlib
import json
import time
from collections.abc import Callable

from pydantic import BaseModel
from sqlalchemy import Engine, case, func, literal, select
from sqlalchemy.orm import Session

from lifegather.auth.models import User
from lifegather.auth.store import Account
from lifegather.config import Settings
from lifegather.database import account_scope, begin_snapshot
from lifegather.documents.models import Document
from lifegather.operations.models import OperationalEvent
from lifegather.photos.models import Photo
from lifegather.scans.models import ScanRun, ScanSchedule
from lifegather.storage.quota import MIB

# A running scan renews its 60-second lease while it works; one this far past
# expiry was not picked up again by any worker.
LEASE_GRACE_SECONDS = 120
QUEUED_SECONDS = 30 * 60
OVERDUE_SECONDS = 60 * 60
WINDOW_SECONDS = 7 * 86400
EVENT_LIMIT = 50
LARGEST_ACCOUNTS = 5


def is_operator(settings: Settings, account: Account) -> bool:
    return account.email.strip().casefold() in settings.operator_email_set


def pseudonym(user_id: str) -> str:
    """A stable short label that does not reveal the account's identity."""
    return "account-" + hashlib.sha256(user_id.encode()).hexdigest()[:8]


class StuckJobs(BaseModel):
    expired_leases: int
    long_queued: int
    overdue_schedules: int

    @property
    def total(self) -> int:
        return self.expired_leases + self.long_queued + self.overdue_schedules


class JobCounts(BaseModel):
    queued: int
    running: int
    completed_7d: int
    failed_7d: int
    canceled_7d: int


class FailureGroup(BaseModel):
    handler: str
    count: int
    last_at: int


class ScheduleCounts(BaseModel):
    enabled: int
    paused: int


class EventSummary(BaseModel):
    level: str
    logger: str
    message: str
    details: dict[str, str | int]
    count: int
    first_at: int
    last_at: int
    alerted_at: int | None


class AccountStorage(BaseModel):
    account: str
    photos: int
    documents: int
    bytes: int


class StorageUse(BaseModel):
    accounts: int
    photos: int
    documents: int
    photo_bytes: int
    document_bytes: int
    total_bytes: int
    largest: list[AccountStorage]
    # LIFEGATHER_STORAGE_QUOTA_MB in bytes; None when accounts have no limit.
    quota_bytes: int | None = None


class AlertChannels(BaseModel):
    webhook: bool
    email: bool


class OperationsOverview(BaseModel):
    checked_at: int
    background_mode: str
    alerts: AlertChannels
    jobs: JobCounts
    stuck: StuckJobs
    failures: list[FailureGroup]
    schedules: ScheduleCounts
    events: list[EventSummary]
    storage: StorageUse


def stuck_jobs(db: Session, now: int) -> StuckJobs:
    return StuckJobs(
        expired_leases=db.scalar(
            select(func.count())
            .select_from(ScanRun)
            .where(
                ScanRun.state == "running",
                ScanRun.lease_until < now - LEASE_GRACE_SECONDS,
            )
        )
        or 0,
        long_queued=db.scalar(
            select(func.count())
            .select_from(ScanRun)
            .where(ScanRun.state == "queued", ScanRun.updated_at < now - QUEUED_SECONDS)
        )
        or 0,
        overdue_schedules=db.scalar(
            select(func.count())
            .select_from(ScanSchedule)
            .where(
                ScanSchedule.enabled.is_(True),
                ScanSchedule.next_run < now - OVERDUE_SECONDS,
            )
        )
        or 0,
    )


class OperationsView:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        alerts: AlertChannels,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.alerts = alerts
        self.clock = clock or (lambda: int(time.time()))

    def stuck(self) -> StuckJobs:
        with account_scope(None), Session(self.engine) as db, db.begin():
            return stuck_jobs(db, self.clock())

    def read(self) -> OperationsOverview:
        now = self.clock()
        since = now - WINDOW_SECONDS
        with account_scope(None), Session(self.engine) as db, db.begin():
            begin_snapshot(db)
            states = dict(
                db.execute(
                    select(ScanRun.state, func.count())
                    .where(
                        ScanRun.state.in_(("queued", "running"))
                        | (ScanRun.updated_at >= since)
                    )
                    .group_by(ScanRun.state)
                ).all()
            )
            failures = [
                FailureGroup(handler=handler, count=count, last_at=last)
                for handler, count, last in db.execute(
                    select(
                        ScanRun.handler_key,
                        func.count(),
                        func.max(ScanRun.updated_at),
                    )
                    .where(ScanRun.state == "failed", ScanRun.updated_at >= since)
                    .group_by(ScanRun.handler_key)
                    .order_by(func.count().desc(), ScanRun.handler_key)
                ).all()
            ]
            enabled, paused = db.execute(
                select(
                    func.count(case((ScanSchedule.enabled.is_(True), 1))),
                    func.count(case((ScanSchedule.enabled.is_(False), 1))),
                )
            ).one()
            events = [
                EventSummary(
                    level=row.level,
                    logger=row.logger,
                    message=row.message,
                    details=json.loads(row.detail_json),
                    count=row.count,
                    first_at=row.first_at,
                    last_at=row.last_at,
                    alerted_at=row.alerted_at,
                )
                for row in db.scalars(
                    select(OperationalEvent)
                    .order_by(
                        OperationalEvent.last_at.desc(), OperationalEvent.fingerprint
                    )
                    .limit(EVENT_LIMIT)
                )
            ]
            return OperationsOverview(
                checked_at=now,
                background_mode=self.settings.background_mode,
                alerts=self.alerts,
                jobs=JobCounts(
                    queued=states.get("queued", 0),
                    running=states.get("running", 0),
                    completed_7d=states.get("completed", 0),
                    failed_7d=states.get("failed", 0),
                    canceled_7d=states.get("canceled", 0),
                ),
                stuck=stuck_jobs(db, now),
                failures=failures,
                schedules=ScheduleCounts(enabled=enabled, paused=paused),
                events=events,
                storage=self._storage(db),
            )

    def _storage(self, db: Session) -> StorageUse:
        photos = (
            select(
                Photo.user_id.label("user_id"),
                func.count().label("photos"),
                literal(0).label("documents"),
                func.sum(Photo.size + Photo.preview_size).label("bytes"),
            )
            .where(Photo.deleted_at.is_(None))
            .group_by(Photo.user_id)
        )
        documents = (
            select(
                Document.user_id.label("user_id"),
                literal(0).label("photos"),
                func.count().label("documents"),
                func.sum(Document.size).label("bytes"),
            )
            .where(Document.deleted_at.is_(None))
            .group_by(Document.user_id)
        )
        files = photos.union_all(documents).subquery()
        per_account = (
            select(
                files.c.user_id,
                func.sum(files.c.photos).label("photos"),
                func.sum(files.c.documents).label("documents"),
                func.sum(files.c.bytes).label("bytes"),
            )
            .group_by(files.c.user_id)
            .subquery()
        )
        largest = [
            AccountStorage(
                account=pseudonym(user_id),
                photos=int(photo_count),
                documents=int(document_count),
                bytes=int(size),
            )
            for user_id, photo_count, document_count, size in db.execute(
                select(per_account)
                .order_by(per_account.c.bytes.desc(), per_account.c.user_id)
                .limit(LARGEST_ACCOUNTS)
            ).all()
        ]
        photo_count, photo_bytes = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Photo.size + Photo.preview_size), 0),
            ).where(Photo.deleted_at.is_(None))
        ).one()
        document_count, document_bytes = db.execute(
            select(func.count(), func.coalesce(func.sum(Document.size), 0)).where(
                Document.deleted_at.is_(None)
            )
        ).one()
        return StorageUse(
            accounts=db.scalar(select(func.count()).select_from(User)) or 0,
            photos=photo_count,
            documents=document_count,
            photo_bytes=int(photo_bytes),
            document_bytes=int(document_bytes),
            total_bytes=int(photo_bytes) + int(document_bytes),
            largest=largest,
            quota_bytes=self.settings.storage_quota_mb * MIB or None,
        )
