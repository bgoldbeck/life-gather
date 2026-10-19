import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from test_reconciliation import setup

from lifegather.auth.store import Account
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.scans.registry import (
    PreparedScan,
    ScanBatch,
    ScanContext,
    ScanEvidence,
    ScanRegistry,
)
from lifegather.scans.service import LeaseLost, ScanService
from lifegather.scans.worker import ScanWorker


class SyntheticConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(default=3, ge=1, le=5)


class SyntheticHandler:
    key = "synthetic"
    title = "Synthetic test evidence"
    permissions = ("synthetic-test-only",)
    config_model = SyntheticConfig

    def prepare(self, actor: Account, config: BaseModel) -> PreparedScan:
        return PreparedScan("synthetic", config.model_dump())

    def window(self, config: dict[str, Any], since: int, until: int) -> dict[str, Any]:
        return config

    def authorize(self, db: Session, actor: Account, config: dict[str, Any]) -> None:
        pass

    async def step(
        self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
    ) -> ScanBatch:
        context.check()
        index = int(cursor.get("index", 0))
        return ScanBatch(
            [
                ScanEvidence(
                    key=str(index),
                    source=SourceInput(
                        text=f"Synthetic evidence {index}",
                        source_type="import",
                        namespace="synthetic-scans",
                        external_id=str(index),
                    ),
                    label=f"Synthetic record {index}",
                )
            ],
            {"index": index + 1} if index + 1 < config["count"] else None,
        )


def registry() -> ScanRegistry:
    return ScanRegistry([SyntheticHandler()])


def test_registry_and_scan_owner_replay_overlap_cancel(tmp_path: Path) -> None:
    auth, alice, bob, _, _ = setup(tmp_path)
    scans = ScanService(auth.engine, registry(), clock=lambda: 100)
    with pytest.raises(MemoryError):
        scans.enqueue(alice, "unknown", {}, "unknown")
    run = scans.enqueue(alice, "synthetic", {"count": 2}, "first")
    assert scans.enqueue(alice, "synthetic", {"count": 2}, "first") == run
    with pytest.raises(MemoryError):
        scans.enqueue(alice, "synthetic", {"count": 3}, "first")
    with pytest.raises(MemoryError, match="already"):
        scans.enqueue(alice, "synthetic", {"count": 2}, "overlap")
    assert scans.list(bob)["items"] == []
    with pytest.raises(MemoryError):
        scans.get(bob, run["id"])
    canceled = scans.cancel(alice, run["id"])
    assert canceled["state"] == "canceled"
    assert scans.claim() is None
    auth.engine.dispose()


def test_worker_saves_evidence_idempotently_without_assets(tmp_path: Path) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    scans = ScanService(auth.engine, registry(), clock=lambda: 100)
    worker = ScanWorker(scans)
    first = scans.enqueue(actor, "synthetic", {"count": 3}, "first")
    assert asyncio.run(worker.run_once())
    row = scans.get(actor, first["id"])
    assert row["state"] == "completed" and row["scanned"] == row["imported"] == 3
    assert len(row["items"]) == 3
    second = scans.enqueue(actor, "synthetic", {"count": 3}, "second")
    asyncio.run(worker.run_once())
    repeated = scans.get(actor, second["id"])
    assert repeated["imported"] == 0 and repeated["existing"] == 3
    assert len(memory.export_page(actor, "sources")["items"]) == 3
    assert reconcile.inventory(actor) == []
    auth.engine.dispose()


def test_expired_claim_resumes_checkpoint_and_refuses_old_worker(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    now = [100]
    scans = ScanService(auth.engine, registry(), clock=lambda: now[0])
    run = scans.enqueue(actor, "synthetic", {"count": 3}, "restart")
    first = scans.claim()
    assert first is not None
    context = ScanContext(
        actor, run["id"], lambda: scans.heartbeat(run["id"], first.token)
    )
    batch = asyncio.run(SyntheticHandler().step(context, first.config, first.cursor))
    scans.commit_batch(first, batch)
    now[0] = 161
    with pytest.raises(LeaseLost):
        scans.heartbeat(run["id"], first.token)
    asyncio.run(ScanWorker(scans).run_once())
    row = scans.get(actor, run["id"])
    assert row["state"] == "completed" and row["imported"] == 3
    assert row["attempts"] == 2
    auth.engine.dispose()
