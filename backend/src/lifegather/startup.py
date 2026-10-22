"""Lock-guarded startup tasks shared by the app and the one-shot migrate job."""

from dataclasses import dataclass
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from lifegather.auth.store import AuthStore
from lifegather.credentials.service import VaultKeyring, rotate_vault_key
from lifegather.legacy_import import import_on_start
from lifegather.storage.base import ObjectStorage
from lifegather.storage.originals import move_inline_originals

# Distinct from the per-transaction writer lock in lifegather.database.
STARTUP_LOCK = 0x4C47_5354  # "LGST"
MIGRATIONS = Path(__file__).parent / "migrations"


class StartupError(RuntimeError):
    pass


@dataclass(frozen=True)
class StartupResult:
    imported_rows: int | None
    vault_rotated: bool


def head_revision() -> str | None:
    return ScriptDirectory(str(MIGRATIONS)).get_current_head()


def schema_current(engine: Engine) -> bool:
    """True when the database answers and is at this release's schema head."""
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current is not None and current == head_revision()


def run_startup_tasks(
    store: AuthStore,
    storage: ObjectStorage,
    data_dir: Path,
    keyring: VaultKeyring | None,
) -> StartupResult:
    """Import, migrate, move inline files and rotate the vault key, once at a time.

    A session advisory lock serializes every instance and migrate job, so two
    containers starting together never race; the second finds the work done.
    """
    with store.engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(:key)"), {"key": STARTUP_LOCK})
        try:
            counts = import_on_start(data_dir, store.engine)
            store.migrate()
            move_inline_originals(store.engine, storage)
            rotated = (
                rotate_vault_key(store.engine, keyring)
                if keyring is not None
                else False
            )
        finally:
            # Session locks outlive transactions; release before pooling.
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": STARTUP_LOCK})
            lock.commit()
    return StartupResult(sum(counts.values()) if counts is not None else None, rotated)
