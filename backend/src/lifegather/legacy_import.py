"""One-time copy of a pre-PostgreSQL installation database into PostgreSQL.

Releases up to 0.74 stored everything in `<data_dir>/auth.sqlite3`. The copy
runs in one PostgreSQL transaction into an empty database, verifies row counts
and rebuilds the search terms. The SQLite file is opened read-only and is never
changed or deleted, so a failed import can simply be retried.
"""

import argparse
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, MetaData, create_engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from lifegather.config import Settings
from lifegather.database import begin_serialized, create_database_engine
from lifegather.memory.backup import (
    application_tables,
    load_tables,
    migrate_to,
    require_empty,
)
from lifegather.memory.search_index import terms

LEGACY_FILE = "auth.sqlite3"
# The last SQLite schemas; older installations first start a 0.74 release once.
SUPPORTED_MIGRATIONS = frozenset(
    {"0027_forest_dark_theme", "0028_object_storage", "0029_receipt_detail_basis"}
)
SEARCH_TABLE = "memory_fts"


class LegacyImportError(ValueError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def check_legacy(path: Path) -> tuple[str, dict[str, int]]:
    """Integrity, schema version and headline counts of a SQLite database."""
    migration = _check(path)
    try:
        with closing(_connect(path)) as db:
            counts = {
                name: int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for name, table in (
                    ("users", "users"),
                    ("credentials", "credentials"),
                    ("photos", "photos"),
                    ("documents", "documents"),
                )
            }
    except sqlite3.Error:
        raise LegacyImportError("Unable to read the SQLite database") from None
    return migration, counts


def _check(path: Path) -> str:
    try:
        with closing(_connect(path)) as db:
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise LegacyImportError(
                    "The SQLite database failed its integrity check"
                )
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise LegacyImportError("The SQLite database has broken references")
            revisions = db.execute(
                "SELECT version_num FROM alembic_version LIMIT 2"
            ).fetchall()
    except sqlite3.Error:
        raise LegacyImportError("Unable to read the SQLite database") from None
    if len(revisions) != 1 or revisions[0][0] not in SUPPORTED_MIGRATIONS:
        raise LegacyImportError(
            "Start LifeGather 0.74 once on this data to finish its SQLite "
            "migrations, then import"
        )
    return str(revisions[0][0])


def import_legacy(path: Path, engine: Engine) -> dict[str, int] | None:
    """Copy `path` into an empty PostgreSQL database; None if it has a schema."""
    migration = _check(path)
    source = create_engine(
        "sqlite://", creator=lambda: _connect(path), poolclass=NullPool
    )
    try:
        with source.connect() as legacy, engine.begin() as target:
            begin_serialized(target)
            if inspect(target).has_table("alembic_version"):
                return None
            require_empty(target)
            legacy.exec_driver_sql("BEGIN")
            reflected = MetaData()
            reflected.reflect(legacy)
            migrate_to(target, migration)
            tables = application_tables(target)
            expected: dict[str, int] = {}
            rows: dict[str, Iterator[dict[str, Any]]] = {}
            for table in tables:
                columns = list(table.columns.keys())
                if table.name == SEARCH_TABLE:
                    count = legacy.scalar(text("SELECT count(*) FROM memory_fts"))
                    rows[table.name] = (
                        {
                            "record_id": record,
                            "user_id": owner,
                            "kind": kind,
                            "body": body,
                            "terms": terms(body),
                        }
                        for record, owner, kind, body in legacy.execute(
                            text("SELECT record_id,user_id,kind,body FROM memory_fts")
                        )
                    )
                else:
                    old = reflected.tables.get(table.name)
                    if old is None or set(old.columns.keys()) != set(columns):
                        raise LegacyImportError(
                            "The SQLite schema does not match its recorded version"
                        )
                    count = legacy.scalar(select(text("count(*)")).select_from(old))
                    rows[table.name] = (
                        dict(row._mapping)
                        for row in legacy.execution_options(yield_per=200).execute(
                            select(*(old.c[name] for name in columns))
                        )
                    )
                expected[table.name] = int(count or 0)
            counts = load_tables(target, tables, rows)
            if counts != expected:
                raise LegacyImportError("Imported row counts do not match SQLite")
            return counts
    except (LegacyImportError, SQLAlchemyError):
        raise
    except (sqlite3.Error, OSError):
        raise LegacyImportError("Unable to read the SQLite database") from None
    finally:
        source.dispose()


def import_on_start(data_dir: Path, engine: Engine) -> dict[str, int] | None:
    """Import an existing SQLite installation the first time PostgreSQL is used."""
    path = data_dir / LEGACY_FILE
    if not path.is_file():
        return None
    with engine.connect() as connection:
        if inspect(connection).has_table("alembic_version"):
            return None
    counts = import_legacy(path, engine)
    if counts is not None:
        print(
            f"Imported {sum(counts.values())} rows from {path} into PostgreSQL. "
            "The SQLite file was left unchanged; remove it once you have "
            "checked the imported data and taken a new backup.",
            file=sys.stderr,
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lifegather.legacy_import",
        description="Copy a SQLite LifeGather database into empty PostgreSQL.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "sqlite",
        type=Path,
        nargs="?",
        help="Path to auth.sqlite3 (default: <data_dir>/auth.sqlite3)",
    )
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = Settings()
        path = args.sqlite or settings.data_dir / LEGACY_FILE
        if not path.is_file():
            print(f"No SQLite database at {path}", file=sys.stderr)
            return 1
        engine = create_database_engine(settings.database())
        counts = import_legacy(path, engine)
        if counts is None:
            print(
                "PostgreSQL already has a LifeGather schema; nothing imported.",
                file=sys.stderr,
            )
            return 1
        print(f"Imported {sum(counts.values())} rows in {len(counts)} tables.")
        return 0
    except (LegacyImportError, ValueError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
    except SQLAlchemyError:
        print(
            "Import failed and was rolled back. Check the database URL and that "
            "the PostgreSQL database is empty.",
            file=sys.stderr,
        )
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
