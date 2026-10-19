from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_reconciliation import setup

from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError
from lifegather.purchases.schemas import EvidenceSave, EvidenceWithdraw
from lifegather.purchases.service import PurchaseEvidenceService


def test_revisions_paging_withdrawal_replay_and_tenant_foreign_keys(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _ = setup(tmp_path)
    service = PurchaseEvidenceService(auth.engine)
    source = memory.ingest(actor, SourceInput(text="Synthetic Store order P1"))
    base = EvidenceSave(
        source_id=source.id,
        role="order",
        retailer="Synthetic Store",
        account_scope="mine",
        order_id="P1",
        quote=source.text,
        reason="Synthetic",
        request_id="0",
    )
    head = service.save(actor, base)
    for index in range(1, 7):
        head = service.save(
            actor,
            base.model_copy(
                update={"expected_head": head["id"], "request_id": str(index)}
            ),
        )
    newest = service.history(actor, source.id)
    assert len(newest["items"]) == 5 and newest["next_revision"] == 3
    assert [
        row["revision"] for row in service.history(actor, source.id, 3)["items"]
    ] == [2, 1]
    withdraw = EvidenceWithdraw(
        source_id=source.id,
        expected_head=head["id"],
        reason="Withdraw duplicate claim",
        request_id="withdraw",
    )
    withdrawn = service.withdraw(actor, withdraw)
    assert service.withdraw(actor, withdraw) == withdrawn
    with pytest.raises(MemoryError):
        service.save(
            actor,
            base.model_copy(
                update={"expected_head": head["id"], "request_id": "stale-restore"}
            ),
        )
    restored = service.save(
        actor,
        base.model_copy(
            update={"expected_head": withdrawn["id"], "request_id": "restore"}
        ),
    )
    assert restored["revision"] == 9
    with auth.engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text("UPDATE purchase_evidence SET user_id=:owner WHERE id=:id"),
            {"owner": bob.id, "id": restored["id"]},
        )
    # Source and account scope are both private identity boundaries.
    other = service.save(
        actor,
        base.model_copy(
            update={
                "expected_head": restored["id"],
                "account_scope": "another-account",
                "request_id": "other-account",
            }
        ),
    )
    assert other["purchase_id"] != restored["purchase_id"]
    first_page = service.list(actor, limit=1)
    assert first_page["next_cursor"] is not None
    assert len(service.list(actor, first_page["next_cursor"], 1)["items"]) == 1
    auth.engine.dispose()


@pytest.mark.usefixtures("legacy_audit_writer")
def test_migration_preserves_existing_canonical_purchase(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config
    from test_reconciliation import discovery

    import lifegather
    from lifegather.auth.store import AuthStore
    from lifegather.memory.service import MemoryService
    from lifegather.reconciliation.service import ReconciliationService

    store = AuthStore(tmp_path / "legacy.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0019_scan_schedules")
    actor = store.login("legacy", "legacy@example.test", "Synthetic", now=1).user
    memory = MemoryService(store.engine)
    before = ReconciliationService(store.engine).discover(
        actor, discovery(memory, actor)
    )
    store.migrate()
    service = PurchaseEvidenceService(store.engine)
    purchase = service.list(actor)["items"][0]
    assert service.get(actor, purchase["id"])["linked_asset_ids"] == before.asset_ids
    assert service.get(actor, purchase["id"])["items"] == []
    store.engine.dispose()
