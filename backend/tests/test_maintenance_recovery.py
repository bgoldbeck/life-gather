from pathlib import Path

import pytest
from sqlalchemy import text
from test_maintenance import plan, prepared

from lifegather.maintenance.service import MaintenanceService
from lifegather.recovery.database import validate_database
from lifegather.recovery.envelope import RecoveryError


@pytest.mark.parametrize("damage", ["missing_tables", "missing_head"])
def test_recovery_refuses_incomplete_current_maintenance_storage(
    tmp_path: Path, damage: str
) -> None:
    store, alice, _, vehicle = prepared(tmp_path)
    task = MaintenanceService(store.engine).create(alice, plan(vehicle))
    migration = validate_database(store.engine, None).migration
    assert migration == "0041_photo_galleries"
    with store.engine.begin() as db:
        if damage == "missing_tables":
            db.exec_driver_sql("DROP TABLE maintenance_revisions")
            db.exec_driver_sql("DROP TABLE maintenance_tasks")
        else:
            db.execute(
                text("DELETE FROM maintenance_revisions WHERE task_id=:id"),
                {"id": task["id"]},
            )
    with pytest.raises(RecoveryError):
        validate_database(store.engine, None)
    store.engine.dispose()
