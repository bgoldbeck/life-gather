"""One bounded async runner; handlers never control job ownership or recurrence."""

import asyncio
from collections.abc import Callable

from sqlalchemy.exc import OperationalError

from lifegather.memory.origins import change_origin
from lifegather.scans.registry import ScanContext
from lifegather.scans.service import LeaseLost, ScanCanceled, ScanService


class ScanWorker:
    def __init__(
        self, scans: ScanService, dispatch: Callable[[], int] | None = None
    ) -> None:
        self.scans = scans
        self.dispatch = dispatch

    async def run_once(self) -> bool:
        if self.dispatch:
            self.dispatch()
        claim = self.scans.claim()
        if claim is None:
            return False
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
        except ScanCanceled:
            self.scans.finish(claim, "canceled")
        except LeaseLost:
            pass
        except asyncio.CancelledError:
            self.scans.release(claim)
            raise
        except Exception:
            # Provider exception strings may contain private request material.
            self.scans.finish(
                claim,
                "failed",
                "Scan stopped. Check the connection and requested scope, then retry. "
                "Completed evidence is retained.",
            )
        return True

    async def serve(self) -> None:
        while True:
            try:
                await self.run_once()
            except OperationalError:
                # A transient SQLite lock must not permanently kill background work.
                # Durable leases/checkpoints remain authoritative on the next tick.
                await asyncio.sleep(5)
            await asyncio.sleep(1)
