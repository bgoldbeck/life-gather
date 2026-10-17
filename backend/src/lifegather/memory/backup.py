"""Operator-only whole-database snapshot; never expose as a personal-data tool."""

import os
import sqlite3
from pathlib import Path

from sqlalchemy import Engine


def operator_snapshot(engine: Engine, destination: Path) -> None:
    """Online SQLite backup to a new protected file, including consistent FTS data."""
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        raw = engine.raw_connection()
        try:
            source = raw.driver_connection
            if not isinstance(source, sqlite3.Connection):
                raise ValueError("Snapshot requires SQLite")
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Snapshot integrity check failed")
            finally:
                target.close()
        finally:
            raw.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
