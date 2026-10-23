"""One bounded async runner; handlers never control job ownership or recurrence."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import OperationalError

from lifegather.credentials.service import ReconnectRequired
from lifegather.database import account_scope
from lifegather.memory.origins import ChangeOrigin, change_origin
from lifegather.scans.registry import ScanContext
from lifegather.scans.service import LeaseLost, ScanCanceled, ScanClaim, ScanService

Outcome = Literal["idle", "ran", "paused"]


@dataclass(frozen=True)
class TickReport:
    """Content-free counts from one externally scheduled tick."""

    dispatched: int
    ran: int
    paused: int
    stopped: Literal["idle", "time_limit"]


class ScanWorker:
    def __init__(
        self, scans: ScanService, dispatch: Callable[[], int] | None = None
    ) -> None:
        self.scans = scans
        self.dispatch = dispatch

    async def run_once(self) -> bool:
        if self.dispatch:
            self.dispatch()
        return await self._run_next(None) != "idle"

    async def _run_next(self, deadline: float | None) -> Outcome:
        claim = self.scans.claim()
        if claim is None:
            return "idle"
        # Claiming and dispatch see every account; the job itself sees only
        # its owner's rows and files.
        with account_scope(claim.actor.id):
            return await self._run(claim, deadline)

    async def _run(self, claim: ScanClaim, deadline: float | None) -> Outcome:
        context = ScanContext(
            claim.actor,
            claim.id,
            lambda: self.scans.heartbeat(claim.id, claim.token),
        )
        try:
            handler = self.scans.registry.get(claim.handler_key)
            cursor = claim.cursor
            with change_origin(**self.scans.origin_for(claim)):
                async with asyncio.timeout(600):
                    while True:
                        context.check()
                        batch = await handler.step(context, claim.config, cursor)
                        self.scans.commit_batch(claim, batch)
                        if batch.next_cursor is None:
                            break
                        cursor = batch.next_cursor
                        if deadline is not None and time.monotonic() >= deadline:
                            # The checkpoint is saved; the next tick resumes it.
                            self.scans.pause(claim)
                            return "paused"
        except ScanCanceled:
            self.scans.finish(claim, "canceled")
        except LeaseLost:
            pass
        except asyncio.CancelledError:
            self.scans.release(claim)
            raise
        except ReconnectRequired as error:
            # Fixed text naming the refused sign-in; completed evidence stays.
            self.scans.finish(claim, "failed", str(error))
        except Exception:
            # Provider exception strings may contain private request material.
            self.scans.finish(
                claim,
                "failed",
                "Scan stopped. Check the connection and requested scope, then retry. "
                "Completed evidence is retained.",
            )
        return "ran"

    async def tick(self, seconds: float) -> TickReport:
        """Dispatch due schedules, then run queued scans until the time limit.

        A scan still running at the limit stops after its current step and waits
        in the queue for the next tick, so a tick overruns by at most one step.
        """
        deadline = time.monotonic() + seconds
        # Start from the neutral origin and the trusted system context, as the
        # in-process loop does: an HTTP tick is never a web account request.
        with account_scope(None), change_origin(**ChangeOrigin().model_dump()):
            return await self._tick(deadline)

    async def _tick(self, deadline: float) -> TickReport:
        dispatched = self.dispatch() if self.dispatch else 0
        ran = paused = 0
        while time.monotonic() < deadline:
            outcome = await self._run_next(deadline)
            if outcome == "idle":
                return TickReport(dispatched, ran, paused, "idle")
            if outcome == "paused":
                paused += 1
            else:
                ran += 1
        return TickReport(dispatched, ran, paused, "time_limit")

    async def serve(self) -> None:
        while True:
            try:
                await self.run_once()
            except OperationalError:
                # A transient database error must not permanently kill background work.
                # Durable leases/checkpoints remain authoritative on the next tick.
                await asyncio.sleep(5)
            await asyncio.sleep(1)
