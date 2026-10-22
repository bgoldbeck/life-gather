"""One-shot startup job: python -m lifegather.migrate.

Runs the same lock-guarded tasks the app runs at startup, so deployments that set
LIFEGATHER_MIGRATE_ON_START=false can migrate once before starting instances.
"""

import argparse
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.credentials.service import VaultError, read_keyring
from lifegather.database import DatabaseConfigurationError
from lifegather.startup import run_startup_tasks
from lifegather.storage.base import StorageError
from lifegather.storage.settings import storage_from_settings


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="python -m lifegather.migrate",
        description="Upgrade the database and finish startup tasks, then exit.",
        allow_abbrev=False,
    ).parse_args(argv)
    store: AuthStore | None = None
    try:
        settings = Settings()
        keyring = read_keyring(settings)
        storage = storage_from_settings(settings)
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = AuthStore(settings.database())
        result = run_startup_tasks(store, storage, settings.data_dir, keyring)
    except (
        ValidationError,
        DatabaseConfigurationError,
        VaultError,
        StorageError,
        ValueError,
        SQLAlchemyError,
        OSError,
    ) as error:
        # Messages are fixed strings; settings errors hide their input values.
        reason = (
            "invalid settings"
            if isinstance(error, ValidationError)
            else "database error"
            if isinstance(error, SQLAlchemyError)
            else str(error)
        )
        print(f"Migration failed: {reason}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.engine.dispose()
    if result.imported_rows is not None:
        print(f"Imported {result.imported_rows} legacy rows.", file=sys.stderr)
    if result.vault_rotated and keyring is not None:
        print(
            f"Re-encrypted credentials with vault key '{keyring.active_id}'.",
            file=sys.stderr,
        )
    print("Database is ready.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
