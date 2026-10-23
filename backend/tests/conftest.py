from collections.abc import Iterator
from pathlib import Path

import database_support
import pytest


@pytest.fixture(scope="session", autouse=True)
def postgresql_server() -> Iterator[None]:
    database_support.start()
    yield
    database_support.finish()


@pytest.fixture(autouse=True)
def drop_test_databases() -> Iterator[None]:
    yield
    database_support.drop_created()


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "false")
    monkeypatch.setenv("LIFEGATHER_BUILD_REVISION", "")
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(
        "LIFEGATHER_DATABASE_URL", database_support.database(tmp_path / "data")
    )
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("LIFEGATHER_PUBLIC_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", "")
    monkeypatch.setenv("LIFEGATHER_VAULT_KEYS", "")
    monkeypatch.setenv("LIFEGATHER_TRUSTED_PROXIES", "")
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", "")
    monkeypatch.setenv("LIFEGATHER_MIGRATE_ON_START", "true")
    monkeypatch.setenv("LIFEGATHER_BACKGROUND_MODE", "inprocess")
    monkeypatch.setenv("LIFEGATHER_JOB_TICK_TOKEN", "")
    monkeypatch.setenv("LIFEGATHER_CONFIGURATION_FILE", "")

    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SENDER"):
        monkeypatch.setenv("LIFEGATHER_" + name, "")


@pytest.fixture
def legacy_audit_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed pre-0022 migration fixtures using the historical audit table shape.

    Modern services otherwise include the new mapped column while these tests
    deliberately run against an old database. Preserve real legacy audit rows;
    delegate to the production writer as soon as the fixture is upgraded.
    """
    from uuid import uuid4

    from sqlalchemy import inspect, literal, select, text
    from sqlalchemy.orm import Session

    from lifegather.assets import identity
    from lifegather.auth.store import Account
    from lifegather.memory.service import MemoryService
    from lifegather.reconciliation import inventory
    from lifegather.reconciliation import service as reconciliation_service

    # These fixtures deliberately seed schemas from before identity groups existed.
    # Their records have no consolidations, before or after upgrade. Exercise the
    # historical identity contract while new consolidation tests cover 0023 itself.
    monkeypatch.setattr(identity, "identity_group", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        inventory, "same_identity", lambda actor, left, right: left == right
    )
    monkeypatch.setattr(
        reconciliation_service,
        "same_identity",
        lambda actor, left, right: left == right,
    )
    monkeypatch.setattr(
        reconciliation_service, "secondary_ids", lambda actor: select(literal(None))
    )

    original = MemoryService._audit

    def write(
        self: MemoryService,
        db: Session,
        actor: Account,
        operation: str,
        target: str,
        now: int,
    ) -> None:
        columns = inspect(db.connection()).get_columns("memory_audit")
        if any(column["name"] == "provenance_json" for column in columns):
            original(self, db, actor, operation, target, now)
        else:
            db.execute(
                text(
                    "INSERT INTO memory_audit "
                    "(id,user_id,operation,target_id,recorded_at) "
                    "VALUES (:id,:user,:operation,:target,:now)"
                ),
                dict(
                    id=str(uuid4()),
                    user=actor.id,
                    operation=operation,
                    target=target,
                    now=now,
                ),
            )

    monkeypatch.setattr(MemoryService, "_audit", write)
