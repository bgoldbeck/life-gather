"""Read-only timelines and dashboards over private validated records.

Charts are views, never a second store of truth: every number here is
recomputed from current records. Money sums only reviewed receipt line totals
in their own currency; nothing is converted, estimated or borrowed from
order totals, so one purchase is never counted twice.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, and_, func, select
from sqlalchemy.orm import Session

from lifegather.assets.identity import secondary_ids
from lifegather.auth.store import Account
from lifegather.database import begin_snapshot
from lifegather.documents.models import Document
from lifegather.maintenance.models import MaintenanceRevision, MaintenanceTask
from lifegather.memory.models import Entity
from lifegather.memory.service import MemoryError
from lifegather.photos.models import Photo
from lifegather.purchases.models import PurchaseEvidence
from lifegather.purchases.service import PurchaseEvidenceService
from lifegather.reconciliation.models import Purchase
from lifegather.reconciliation.receipt_models import ReceiptDetail, ReceiptProposal
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService

# Bounds keep one request cheap; a result that reaches one says it is truncated.
LINE_LIMIT = 5000
EVENT_LIMIT = 200
UPCOMING_DAYS = 30
UPCOMING_LIMIT = 10
LARGEST_LIMIT = 5

EventKind = Literal[
    "purchase",
    "order",
    "maintenance_done",
    "maintenance_due",
    "asset",
    "document",
    "photo",
]
KINDS: tuple[EventKind, ...] = (
    "purchase",
    "order",
    "maintenance_done",
    "maintenance_due",
    "asset",
    "document",
    "photo",
)


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always"
    )
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown time zone") from None
        return value


class DashboardRead(Input):
    months: Literal[6, 12, 24] = 12


class TimelineRead(Input):
    month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    kinds: list[EventKind] = Field(default_factory=lambda: list(KINDS), max_length=7)


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_start(key: str) -> date:
    year, month = (int(part) for part in key.split("-"))
    return date(year, month, 1)


def next_month(value: date) -> date:
    return date(value.year + value.month // 12, value.month % 12 + 1, 1)


def month_keys(today: date, count: int) -> list[str]:
    first = date(today.year, today.month, 1)
    keys = []
    for _ in range(count):
        keys.append(month_key(first))
        first = (first - timedelta(days=1)).replace(day=1)
    return keys[::-1]


def micros(day: date, zone: ZoneInfo) -> int:
    """The first microsecond of a local calendar day, as stored recorded_at."""
    moment = datetime(day.year, day.month, day.day, tzinfo=zone)
    return int(moment.timestamp()) * 1_000_000


def local_day(value: int, zone: ZoneInfo) -> date:
    return datetime.fromtimestamp(value / 1_000_000, UTC).astimezone(zone).date()


class InsightsService:
    def __init__(self, engine: Engine, today: date | None = None) -> None:
        self.engine = engine
        self.receipts = ReceiptService(engine)
        self.purchases = PurchaseEvidenceService(engine)
        self.fixed_today = today

    def today(self, zone: ZoneInfo) -> date:
        return self.fixed_today or datetime.now(zone).date()

    def receipt_lines(
        self, db: Session, actor: Account
    ) -> tuple[list[dict[str, Any]], bool]:
        """Current detail of each confirmed purchased line whose source remains."""
        head = (
            select(
                ReceiptDetail.receipt_id,
                ReceiptDetail.line_index,
                func.max(ReceiptDetail.revision).label("revision"),
            )
            .where(ReceiptDetail.user_id == actor.id)
            .group_by(ReceiptDetail.receipt_id, ReceiptDetail.line_index)
            .subquery()
        )
        rows = list(
            db.execute(
                select(ReceiptDetail, ReceiptProposal)
                .join(
                    head,
                    and_(
                        head.c.receipt_id == ReceiptDetail.receipt_id,
                        head.c.line_index == ReceiptDetail.line_index,
                        head.c.revision == ReceiptDetail.revision,
                    ),
                )
                .join(
                    ReceiptProposal,
                    and_(
                        ReceiptProposal.user_id == actor.id,
                        ReceiptProposal.id == ReceiptDetail.receipt_id,
                    ),
                )
                .where(
                    ReceiptDetail.user_id == actor.id,
                    ReceiptProposal.state == "accepted",
                    ReceiptProposal.reviewed_json.is_not(None),
                )
                .order_by(ReceiptDetail.id)
                .limit(LINE_LIMIT + 1)
            )
        )
        truncated = len(rows) > LINE_LIMIT
        reviews: dict[str, ReceiptReview] = {}
        available: dict[str, bool] = {}
        lines = []
        for detail, receipt in rows[:LINE_LIMIT]:
            if receipt.id not in reviews:
                reviews[receipt.id] = ReceiptReview.model_validate_json(
                    receipt.reviewed_json or "{}"
                )
            choice = next(
                (
                    c
                    for c in reviews[receipt.id].choices
                    if c.index == detail.line_index
                ),
                None,
            )
            if choice is None or choice.action == "skip":
                continue
            if choice.fields.kind != "purchase":
                continue
            if receipt.source_id not in available:
                try:
                    self.receipts.source(db, actor, receipt.source_id)
                    available[receipt.source_id] = True
                except MemoryError:
                    available[receipt.source_id] = False
            if not available[receipt.source_id]:
                continue
            lines.append(
                {
                    "receipt_id": receipt.id,
                    "index": detail.line_index,
                    "source_id": receipt.source_id,
                    "name": choice.fields.name,
                    "quantity": choice.fields.quantity,
                    "total_minor": detail.total_minor,
                    "currency": detail.currency,
                    "purchase_date": detail.purchase_date,
                }
            )
        return lines, truncated

    @staticmethod
    def monthly_counts(
        db: Session,
        column: Any,
        conditions: list[Any],
        zone: str,
        start: int,
        end: int,
    ) -> dict[str, int]:
        month = func.to_char(
            func.timezone(zone, func.to_timestamp(column / 1_000_000.0)),
            "YYYY-MM",
        )
        return {
            key: count
            for key, count in db.execute(
                select(month, func.count())
                .where(*conditions, column >= start, column < end)
                .group_by(month)
            )
        }

    def dashboard(self, actor: Account, value: DashboardRead) -> dict[str, Any]:
        data = DashboardRead.model_validate(value)
        zone = ZoneInfo(data.timezone)
        today = self.today(zone)
        months = month_keys(today, data.months)
        first = month_start(months[0])
        end = next_month(month_start(months[-1]))
        start_us, end_us = micros(first, zone), micros(end, zone)
        with Session(self.engine) as db:
            begin_snapshot(db)
            lines, truncated = self.receipt_lines(db, actor)
            index = {key: position for position, key in enumerate(months)}
            spending: dict[str, dict[str, Any]] = {}
            bought = [0] * len(months)
            missing_total = 0
            for line in lines:
                when = line["purchase_date"]
                slot = index.get(when[:7]) if when else None
                if slot is not None:
                    bought[slot] += 1
                    if line["total_minor"] is None:
                        missing_total += 1
                if line["total_minor"] is None:
                    continue
                entry = spending.setdefault(
                    line["currency"],
                    {
                        "currency": line["currency"],
                        "total_minor": 0,
                        "line_count": 0,
                        "by_month": [0] * len(months),
                        "undated_minor": 0,
                        "undated_count": 0,
                        "largest": [],
                    },
                )
                if when is None:
                    entry["undated_minor"] += line["total_minor"]
                    entry["undated_count"] += 1
                elif slot is not None:
                    entry["by_month"][slot] += line["total_minor"]
                    entry["total_minor"] += line["total_minor"]
                    entry["line_count"] += 1
                    entry["largest"].append(line)
            for entry in spending.values():
                entry["largest"] = sorted(
                    entry["largest"],
                    key=lambda line: (-line["total_minor"], line["purchase_date"]),
                )[:LARGEST_LIMIT]

            assets = self.monthly_counts(
                db,
                Entity.recorded_at,
                [
                    Entity.user_id == actor.id,
                    Entity.kind == "asset",
                    Entity.id.not_in(secondary_ids(actor)),
                ],
                data.timezone,
                start_us,
                end_us,
            )
            documents = self.monthly_counts(
                db,
                Document.created_at,
                [Document.user_id == actor.id, Document.deleted_at.is_(None)],
                data.timezone,
                start_us,
                end_us,
            )
            photos = self.monthly_counts(
                db,
                Photo.created_at,
                [Photo.user_id == actor.id, Photo.deleted_at.is_(None)],
                data.timezone,
                start_us,
                end_us,
            )
            completed: defaultdict[str, int] = defaultdict(int)
            for day, count in db.execute(
                select(MaintenanceRevision.completed_on, func.count())
                .where(
                    MaintenanceRevision.user_id == actor.id,
                    MaintenanceRevision.superseded_at.is_(None),
                    MaintenanceRevision.state == "completed",
                    MaintenanceRevision.completed_on >= first,
                    MaintenanceRevision.completed_on < end,
                )
                .group_by(MaintenanceRevision.completed_on)
            ):
                if day is not None:
                    completed[month_key(day)] += count
            upcoming = self.upcoming(db, actor, today)
            return {
                "months": months,
                "today": today.isoformat(),
                "timezone": data.timezone,
                "spending": sorted(
                    spending.values(), key=lambda entry: -entry["total_minor"]
                ),
                "spending_basis": "receipt_line_totals",
                "missing_total_count": missing_total,
                "activity": {
                    "purchase": bought,
                    "asset": [assets.get(key, 0) for key in months],
                    "document": [documents.get(key, 0) for key in months],
                    "photo": [photos.get(key, 0) for key in months],
                    "maintenance_done": [completed.get(key, 0) for key in months],
                },
                **upcoming,
                "truncated": truncated,
            }

    @staticmethod
    def upcoming(db: Session, actor: Account, today: date) -> dict[str, Any]:
        base = (
            select(MaintenanceRevision, MaintenanceTask, Entity)
            .join(
                MaintenanceTask,
                and_(
                    MaintenanceTask.user_id == actor.id,
                    MaintenanceTask.id == MaintenanceRevision.task_id,
                ),
            )
            .join(
                Entity,
                and_(
                    Entity.user_id == actor.id, Entity.id == MaintenanceTask.entity_id
                ),
            )
            .where(
                MaintenanceRevision.user_id == actor.id,
                MaintenanceRevision.superseded_at.is_(None),
                MaintenanceRevision.state == "open",
                MaintenanceRevision.due_on.is_not(None),
            )
        )
        overdue = db.scalar(
            select(func.count()).select_from(
                base.where(MaintenanceRevision.due_on < today).subquery()
            )
        )
        rows = db.execute(
            base.where(
                MaintenanceRevision.due_on <= today + timedelta(days=UPCOMING_DAYS)
            )
            .order_by(MaintenanceRevision.due_on, MaintenanceRevision.id)
            .limit(UPCOMING_LIMIT)
        )
        return {
            "overdue_count": overdue or 0,
            "upcoming": [
                {
                    "task_id": task.id,
                    "title": revision.title,
                    "due_on": revision.due_on.isoformat() if revision.due_on else None,
                    "overdue": bool(revision.due_on and revision.due_on < today),
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "entity_kind": entity.kind,
                }
                for revision, task, entity in rows
            ],
        }

    def timeline(self, actor: Account, value: TimelineRead) -> dict[str, Any]:
        data = TimelineRead.model_validate(value)
        zone = ZoneInfo(data.timezone)
        first = month_start(data.month)
        end = next_month(first)
        start_us, end_us = micros(first, zone), micros(end, zone)
        kinds = set(data.kinds)
        events: list[dict[str, Any]] = []
        truncated = False

        def event(
            kind: EventKind,
            day: date | str,
            basis: Literal["stated", "recorded"],
            title: str,
            target: dict[str, str],
            detail: str = "",
            identifier: str = "",
            amount: tuple[int | None, str | None] = (None, None),
        ) -> None:
            events.append(
                {
                    "id": f"{kind}:{identifier or target['id']}",
                    "kind": kind,
                    "date": day if isinstance(day, str) else day.isoformat(),
                    "date_basis": basis,
                    "title": title,
                    "detail": detail,
                    "amount_minor": amount[0],
                    "currency": amount[1],
                    "target": target,
                }
            )

        def bounded(rows: list[Any]) -> list[Any]:
            nonlocal truncated
            truncated = truncated or len(rows) > EVENT_LIMIT
            return rows[:EVENT_LIMIT]

        with Session(self.engine) as db:
            begin_snapshot(db)
            if "purchase" in kinds:
                lines, cut = self.receipt_lines(db, actor)
                truncated = truncated or cut
                dated = [
                    line
                    for line in lines
                    if line["purchase_date"]
                    and line["purchase_date"].startswith(data.month)
                ]
                for line in bounded(dated):
                    quantity = line["quantity"]
                    event(
                        "purchase",
                        line["purchase_date"],
                        "stated",
                        line["name"],
                        {"view": "Memories", "id": line["source_id"]},
                        f"Qty {quantity}" if quantity > 1 else "",
                        f"{line['receipt_id']}:{line['index']}",
                        (line["total_minor"], line["currency"]),
                    )
            if "order" in kinds:
                rows = list(
                    db.execute(
                        select(PurchaseEvidence, Purchase)
                        .join(
                            Purchase,
                            and_(
                                Purchase.user_id == actor.id,
                                Purchase.id == PurchaseEvidence.purchase_id,
                            ),
                        )
                        .where(
                            PurchaseEvidence.user_id == actor.id,
                            PurchaseEvidence.superseded_at.is_(None),
                            PurchaseEvidence.state == "active",
                            PurchaseEvidence.occurred_on >= first.isoformat(),
                            PurchaseEvidence.occurred_on < end.isoformat(),
                        )
                        .order_by(PurchaseEvidence.occurred_on.desc())
                        .limit(EVENT_LIMIT + 1)
                    )
                )
                for evidence, purchase in bounded(rows):
                    if not self.purchases.current(db, actor, evidence):
                        continue
                    event(
                        "order",
                        evidence.occurred_on or first,
                        "stated",
                        f"{purchase.retailer} order {purchase.order_id}",
                        {"view": "Purchases", "id": purchase.id},
                        evidence.role.capitalize(),
                        evidence.id,
                        (evidence.amount_minor, evidence.currency),
                    )
            if kinds & {"maintenance_done", "maintenance_due"}:
                rows = list(
                    db.execute(
                        select(MaintenanceRevision, Entity)
                        .join(
                            MaintenanceTask,
                            and_(
                                MaintenanceTask.user_id == actor.id,
                                MaintenanceTask.id == MaintenanceRevision.task_id,
                            ),
                        )
                        .join(
                            Entity,
                            and_(
                                Entity.user_id == actor.id,
                                Entity.id == MaintenanceTask.entity_id,
                            ),
                        )
                        .where(
                            MaintenanceRevision.user_id == actor.id,
                            MaintenanceRevision.superseded_at.is_(None),
                            (
                                (MaintenanceRevision.state == "completed")
                                & (MaintenanceRevision.completed_on >= first)
                                & (MaintenanceRevision.completed_on < end)
                            )
                            | (
                                (MaintenanceRevision.state == "open")
                                & (MaintenanceRevision.due_on >= first)
                                & (MaintenanceRevision.due_on < end)
                            ),
                        )
                        .order_by(MaintenanceRevision.id)
                        .limit(EVENT_LIMIT + 1)
                    )
                )
                for revision, entity in bounded(rows):
                    view = "Assets" if entity.kind == "asset" else "Profiles"
                    target = {"view": view, "id": entity.id}
                    if revision.state == "completed" and revision.completed_on:
                        if "maintenance_done" in kinds:
                            event(
                                "maintenance_done",
                                revision.completed_on,
                                "stated",
                                revision.title,
                                target,
                                entity.name,
                                revision.task_id,
                            )
                    elif revision.due_on and "maintenance_due" in kinds:
                        event(
                            "maintenance_due",
                            revision.due_on,
                            "stated",
                            revision.title,
                            target,
                            entity.name,
                            revision.task_id,
                        )
            if "asset" in kinds:
                rows = list(
                    db.scalars(
                        select(Entity)
                        .where(
                            Entity.user_id == actor.id,
                            Entity.kind == "asset",
                            Entity.id.not_in(secondary_ids(actor)),
                            Entity.recorded_at >= start_us,
                            Entity.recorded_at < end_us,
                        )
                        .order_by(Entity.recorded_at.desc())
                        .limit(EVENT_LIMIT + 1)
                    )
                )
                for entity in bounded(rows):
                    event(
                        "asset",
                        local_day(entity.recorded_at, zone),
                        "recorded",
                        entity.name,
                        {"view": "Assets", "id": entity.id},
                    )
            for kind, model in (("document", Document), ("photo", Photo)):
                if kind not in kinds:
                    continue
                files = list(
                    db.execute(
                        select(model.id, model.filename, model.created_at)
                        .where(
                            model.user_id == actor.id,
                            model.deleted_at.is_(None),
                            model.created_at >= start_us,
                            model.created_at < end_us,
                        )
                        .order_by(model.created_at.desc())
                        .limit(EVENT_LIMIT + 1)
                    )
                )
                for identifier, filename, created in bounded(files):
                    event(
                        kind,
                        local_day(created, zone),
                        "recorded",
                        filename,
                        {
                            "view": "Documents" if kind == "document" else "Photos",
                            "id": identifier,
                        },
                    )
        order = {kind: position for position, kind in enumerate(KINDS)}
        # Newest day first; within a day by kind, then title, for a stable view.
        events.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        events.sort(key=lambda item: (item["date"], -order[item["kind"]]), reverse=True)
        return {
            "month": data.month,
            "timezone": data.timezone,
            "items": events,
            "truncated": truncated,
        }
