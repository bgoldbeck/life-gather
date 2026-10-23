"""Backup expiry after account deletion, and the timed restore drill."""

import json
import time
from pathlib import Path

import pytest
from database_support import database
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from lifegather.auth.deletion import delete_account_rows
from lifegather.auth.deletion_ledger import (
    DAY_SECONDS,
    ledger_entries,
    purge_expired,
    record_deletion,
)
from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.database import account_scope
from lifegather.recovery.__main__ import main
from lifegather.recovery.bundle import RecoveryService

NOW = 1_800_000_000


def users(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return set(connection.scalars(text("SELECT id FROM users")))
    finally:
        engine.dispose()


def test_ledger_keeps_ids_until_backups_expire(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path / "ledger"))
    store.migrate()
    alice = store.login("ledger-alice", "alice@example.test", "Alice", now=NOW).user
    expires = record_deletion(store.engine, alice.id, now=NOW, retention_days=35)
    assert expires == NOW + 35 * DAY_SECONDS
    # Recording again (a retried deletion) keeps the first entry.
    record_deletion(store.engine, alice.id, now=NOW + 5, retention_days=1)
    [entry] = ledger_entries(store.engine)
    assert entry.model_dump() == {
        "account_id": alice.id,
        "deleted_at": NOW,
        "backups_expire_at": expires,
    }
    with store.engine.connect() as connection:
        columns = set(
            connection.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'deleted_accounts'"
                )
            )
        )
    assert columns == {"account_id", "deleted_at", "backups_expire_at"}
    with account_scope(alice.id), Session(store.engine) as db:
        with pytest.raises(ProgrammingError):
            db.execute(text("SELECT count(*) FROM deleted_accounts"))
    assert purge_expired(store.engine, now=expires - 1) == 0
    assert purge_expired(store.engine, now=expires) == 1
    assert ledger_entries(store.engine) == []
    store.engine.dispose()


@pytest.fixture
def installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str, str]:
    """A bundle holding Alice and Bob, after which Alice deletes her account."""
    source = tmp_path / "source"
    url = database(source)
    store = AuthStore(url)
    store.migrate()
    alice = store.login("drill-alice", "alice@example.test", "Alice", now=NOW).user
    bob = store.login("drill-bob", "bob@example.test", "Bob", now=NOW).user
    phrase = tmp_path / "phrase"
    phrase.write_bytes(b"synthetic recovery passphrase")
    bundle = tmp_path / "before-deletion.lgbackup"
    RecoveryService(Settings(data_dir=source, database_url=SecretStr(url))).create(
        bundle, phrase.read_bytes()
    )
    with account_scope(alice.id), Session(store.engine) as db:
        delete_account_rows(db, alice.id)
        db.commit()
    record_deletion(store.engine, alice.id, now=NOW, retention_days=35)
    store.engine.dispose()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(source))
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", url)
    return bundle, phrase, alice.id, bob.id


def test_restoring_an_older_backup_erases_later_deletions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installation: tuple[Path, Path, str, str],
) -> None:
    bundle, phrase, alice, bob = installation
    deletions = tmp_path / "deleted.json"
    assert main(["export-deletions", str(deletions)]) == 0
    assert deletions.stat().st_mode & 0o777 == 0o600
    assert main(["export-deletions", str(deletions)]) == 1
    flags = ["--passphrase-file", str(phrase)]
    # Without the list, the older backup brings the deleted account back.
    plain = database(tmp_path / "plain", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", plain)
    assert main(["restore", str(bundle), str(tmp_path / "plain-copy"), *flags]) == 0
    assert alice in users(plain)
    cleaned = database(tmp_path / "cleaned", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", cleaned)
    restored = tmp_path / "cleaned-copy"
    command = ["restore", str(bundle), str(restored), *flags]
    assert main([*command, "--deleted-accounts", str(deletions)]) == 0
    assert users(cleaned) == {bob}
    engine = create_engine(cleaned)
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT account_id FROM deleted_accounts")) == alice
        )
    engine.dispose()


def test_drill_times_a_restore_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    installation: tuple[Path, Path, str, str],
) -> None:
    bundle, phrase, alice, bob = installation
    deletions = tmp_path / "deleted.json"
    assert main(["export-deletions", str(deletions)]) == 0
    staging = tmp_path / "staging"
    staging.mkdir()
    scratch = database(tmp_path / "drill", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", scratch)
    report_file = tmp_path / "drill.json"
    capsys.readouterr()
    code = main(
        [
            "drill",
            str(bundle),
            "--passphrase-file",
            str(phrase),
            "--staging-dir",
            str(staging),
            "--deleted-accounts",
            str(deletions),
            "--report",
            str(report_file),
        ]
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report == json.loads(report_file.read_text(encoding="utf-8"))
    assert report["operation"] == "drill" and report["passed"] is True
    assert report["rpo_target_seconds"] == 24 * 3600
    assert report["rto_target_seconds"] == 3600
    assert 0 <= report["recovery_point_seconds"] < 600
    assert 0 < report["recovery_time_seconds"] < 600
    assert report["past_retention"] is False
    assert report["bundle"]["erased_accounts"] == 1
    assert report["bundle"]["database"]["users"] == 2
    assert users(scratch) == {bob}
    # The restored directory and its staging are gone; nothing private remains.
    assert list(staging.iterdir()) == []
    assert alice not in report_file.read_text(encoding="utf-8")


def test_drill_fails_when_a_target_is_missed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    installation: tuple[Path, Path, str, str],
) -> None:
    bundle, phrase, _, _ = installation
    monkeypatch.setenv(
        "LIFEGATHER_DATABASE_URL", database(tmp_path / "slow", empty=True)
    )
    flags = ["--passphrase-file", str(phrase)]
    assert main(["drill", str(bundle), *flags, "--rto-minutes", "0.00001"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["passed"] is False
    assert "missed its RPO or RTO target" in output.err
    assert main(["drill", str(bundle), *flags, "--rpo-hours", "0"]) == 1
    assert "positive RPO and RTO" in capsys.readouterr().err


def test_drill_flags_bundles_older_than_retention(
    tmp_path: Path, installation: tuple[Path, Path, str, str]
) -> None:
    bundle, phrase, _, _ = installation
    service = RecoveryService(Settings(data_dir=tmp_path / "source"))
    report = service.drill(
        bundle,
        phrase.read_bytes(),
        database(tmp_path / "old", empty=True),
        rpo_target_seconds=3600,
        rto_target_seconds=3600,
        retention_days=35,
        now=lambda: time.time_ns() // 1000 + 40 * DAY_SECONDS * 1_000_000,
    )
    assert report.past_retention is True
    assert report.passed is False
