"""Store captured error events, watch for stuck jobs and send operator alerts.

Alerts name the problem (a fixed message plus route, scan type or error type)
and how often it happened; they never carry personal content. Each kind of
problem alerts at most once an hour, across every process of the installation.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx2
from sqlalchemy import Engine, delete, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lifegather.auth.mail import MailSender
from lifegather.config import Settings
from lifegather.database import account_scope
from lifegather.operations.logs import CAPTURE, EventCapture
from lifegather.operations.models import OperationalEvent
from lifegather.operations.service import AlertChannels, OperationsView, StuckJobs

logger = logging.getLogger("lifegather.operations")

ALERT_INTERVAL_SECONDS = 3600
RETENTION_SECONDS = 30 * 86400
FLUSH_SECONDS = 30
CHECK_EVERY_FLUSHES = 10

Post = Callable[[str, dict[str, Any]], None]


def post_webhook(url: str, payload: dict[str, Any]) -> None:
    response = httpx2.post(url, json=payload, timeout=10, follow_redirects=False)
    response.raise_for_status()


def fingerprint(event: dict[str, Any]) -> str:
    key = json.dumps(
        [event["logger"], event["message"], event["details"]], sort_keys=True
    )
    return hashlib.sha256(key.encode()).hexdigest()


class OperationsMonitor:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        mail_sender: MailSender | None = None,
        *,
        capture: EventCapture = CAPTURE,
        post: Post = post_webhook,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.mail_sender = mail_sender
        self.capture = capture
        self.post = post
        self.clock = clock or (lambda: int(time.time()))

    @property
    def channels(self) -> AlertChannels:
        return AlertChannels(
            webhook=bool(self.settings.alert_webhook_url),
            email=self.mail_sender is not None
            and bool(self.settings.operator_email_set),
        )

    def view(self) -> OperationsView:
        return OperationsView(
            self.engine, self.settings, alerts=self.channels, clock=self.clock
        )

    def check_jobs(self) -> StuckJobs:
        stuck = self.view().stuck()
        if stuck.total:
            logger.error(
                "Background jobs are stuck",
                extra={"job": "scans", "count": stuck.total},
            )
        return stuck

    def flush(self) -> int:
        """Store captured events, then alert for any not alerted this hour."""
        events = self.capture.drain()
        if not events:
            return 0
        now = self.clock()
        due: list[OperationalEvent] = []
        try:
            with (
                account_scope(None),
                Session(self.engine, expire_on_commit=False) as db,
                db.begin(),
            ):
                for event in events:
                    statement = insert(OperationalEvent).values(
                        fingerprint=fingerprint(event),
                        level=event["level"],
                        logger=event["logger"],
                        message=event["message"],
                        detail_json=json.dumps(event["details"], sort_keys=True),
                        count=1,
                        first_at=event["at"],
                        last_at=event["at"],
                        alerted_at=None,
                    )
                    db.execute(
                        statement.on_conflict_do_update(
                            index_elements=[OperationalEvent.fingerprint],
                            set_={
                                "count": OperationalEvent.count + 1,
                                "last_at": statement.excluded.last_at,
                            },
                        )
                    )
                db.execute(
                    delete(OperationalEvent).where(
                        OperationalEvent.last_at < now - RETENTION_SECONDS
                    )
                )
                channels = self.channels
                if channels.webhook or channels.email:
                    keys = sorted({fingerprint(event) for event in events})
                    due = list(
                        db.scalars(
                            update(OperationalEvent)
                            .where(
                                OperationalEvent.fingerprint.in_(keys),
                                or_(
                                    OperationalEvent.alerted_at.is_(None),
                                    OperationalEvent.alerted_at
                                    <= now - ALERT_INTERVAL_SECONDS,
                                ),
                            )
                            .values(alerted_at=now)
                            .returning(OperationalEvent)
                        )
                    )
        except SQLAlchemyError:
            # Keep the events for the next attempt; the database may be restarting.
            self.capture.pending.extendleft(reversed(events))
            logger.warning("Could not store operational events; will retry")
            return 0
        for row in due:
            self._alert(row)
        return len(events)

    def _alert(self, row: OperationalEvent) -> None:
        installation = urlsplit(self.settings.public_url).netloc
        details = json.loads(row.detail_json)
        described = ", ".join(f"{name}: {value}" for name, value in details.items())
        text = (
            f"LifeGather alert on {installation}: {row.message}"
            + (f" ({described})" if described else "")
            + f". Seen {row.count} time{'s' if row.count != 1 else ''}. "
            "Open Operations in LifeGather for details."
        )
        if self.settings.alert_webhook_url:
            try:
                self.post(
                    self.settings.alert_webhook_url,
                    {
                        "text": text,
                        "installation": installation,
                        "level": row.level,
                        "message": row.message,
                        "details": details,
                        "count": row.count,
                        "first_at": row.first_at,
                        "last_at": row.last_at,
                    },
                )
            except (httpx2.HTTPError, OSError, ValueError) as error:
                logger.warning(
                    "Alert webhook delivery failed",
                    extra={"error_type": type(error).__name__},
                )
        if self.mail_sender is not None:
            for recipient in sorted(self.settings.operator_email_set):
                try:
                    self.mail_sender.send(
                        recipient, f"LifeGather alert: {row.message}", text
                    )
                except (OSError, ValueError) as error:
                    logger.warning(
                        "Alert email delivery failed",
                        extra={"error_type": type(error).__name__},
                    )

    async def serve(self) -> None:
        flushes = 0
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            flushes += 1
            try:
                if flushes % CHECK_EVERY_FLUSHES == 0:
                    await asyncio.to_thread(self.check_jobs)
                await asyncio.to_thread(self.flush)
            except SQLAlchemyError:
                logger.warning("Could not check background jobs; will retry")
