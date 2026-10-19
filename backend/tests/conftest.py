from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "false")
    monkeypatch.setenv("LIFEGATHER_BUILD_REVISION", "")
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("LIFEGATHER_PUBLIC_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", "")

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

    from sqlalchemy import inspect, text
    from sqlalchemy.orm import Session

    from lifegather.auth.store import Account
    from lifegather.memory.service import MemoryService

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
