"""Per-account chat conversation retention; saved evidence is never touched."""

import asyncio
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, Select, case, delete, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.chat.models import Conversation, Turn
from lifegather.credentials.models import UserSettings
from lifegather.memory.origins import change_origin
from lifegather.memory.service import MemoryService

Days = Literal[30, 90, 365]
DAY = 86_400_000_000  # The memory clock counts microseconds.
BATCH = 200

logger = logging.getLogger(__name__)


class RetentionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    conversation_days: Days | None


class ConversationRetention:
    """Deletes conversations idle longer than the owner's chosen period.

    Activity is the newest saved request, or creation for an empty conversation.
    Conversations with pending requests wait for them to finish. Each deletion
    writes the same content-free `conversation_deleted` receipt as a reviewed
    delete; memories, sources, originals and records always remain.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.memory = MemoryService(engine)

    def days(self, actor: Account) -> int | None:
        with Session(self.engine) as db:
            return db.scalar(
                select(UserSettings.conversation_retention_days).where(
                    UserSettings.user_id == actor.id
                )
            )

    @staticmethod
    def _expired(user_id: str, days: int, now: int) -> Select[str]:
        activity = (
            select(
                Turn.conversation_id.label("conversation_id"),
                func.max(Turn.created_at).label("last"),
                func.sum(case((Turn.state == "pending", 1), else_=0)).label("pending"),
            )
            .where(Turn.user_id == user_id)
            .group_by(Turn.conversation_id)
            .subquery()
        )
        return (
            select(Conversation.id)
            .outerjoin(activity, activity.c.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user_id,
                func.coalesce(activity.c.last, Conversation.created_at)
                < now - days * DAY,
                func.coalesce(activity.c.pending, 0) == 0,
            )
        )

    def preview(self, actor: Account, days: int | None) -> dict[str, Any]:
        """How many conversations a setting would remove if applied now."""
        data = RetentionInput.model_validate({"conversation_days": days})
        if data.conversation_days is None:
            return {"conversation_days": None, "eligible_count": 0}
        query = self._expired(actor.id, data.conversation_days, self.memory.clock())
        with Session(self.engine) as db:
            count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {"conversation_days": data.conversation_days, "eligible_count": count}

    def _delete_expired(self, user_id: str, days: int) -> int:
        actor = Account(id=user_id, email="", name="")
        deleted = 0
        while True:
            with self.memory._write() as db:
                now = self.memory.clock()
                found = list(
                    db.scalars(
                        self._expired(user_id, days, now)
                        .order_by(Conversation.id)
                        .limit(BATCH)
                    )
                )
                if found:
                    db.execute(
                        delete(Turn).where(
                            Turn.user_id == user_id, Turn.conversation_id.in_(found)
                        )
                    )
                    db.execute(
                        delete(Conversation).where(
                            Conversation.user_id == user_id,
                            Conversation.id.in_(found),
                        )
                    )
                    for identifier in found:
                        self.memory._audit(
                            db, actor, "conversation_deleted", identifier, now
                        )
            deleted += len(found)
            if len(found) < BATCH:
                return deleted

    def update(self, actor: Account, value: RetentionInput) -> dict[str, Any]:
        data = RetentionInput.model_validate(value)
        with self.memory._write() as db:
            row = db.get(UserSettings, actor.id)
            if row is None:
                db.add(
                    UserSettings(
                        user_id=actor.id,
                        allow_external_ai=False,
                        conversation_retention_days=data.conversation_days,
                    )
                )
            else:
                row.conversation_retention_days = data.conversation_days
            self.memory._audit(
                db, actor, "retention_changed", actor.id, self.memory.clock()
            )
        deleted = 0
        if data.conversation_days is not None:
            with change_origin(interface="web", initiator="account_request"):
                deleted = self._delete_expired(actor.id, data.conversation_days)
        return {"conversation_days": data.conversation_days, "deleted_count": deleted}

    def sweep(self) -> int:
        """Apply every account's retention; safe to repeat at any time."""
        with Session(self.engine) as db:
            owners = db.execute(
                select(
                    UserSettings.user_id, UserSettings.conversation_retention_days
                ).where(UserSettings.conversation_retention_days.is_not(None))
            ).all()
        deleted = 0
        with change_origin(interface="scheduler", initiator="scheduled"):
            for user_id, days in owners:
                if days is not None:
                    deleted += self._delete_expired(user_id, days)
        return deleted


async def retention_sweeps(engine: Engine, interval: float = 3600) -> None:
    """Apply retention on startup and then hourly until cancelled."""
    retention = ConversationRetention(engine)
    while True:
        try:
            await asyncio.to_thread(retention.sweep)
        except Exception:
            # A failed sweep is retried at the next interval; chat keeps working.
            logger.exception("Conversation retention sweep failed")
        await asyncio.sleep(interval)
