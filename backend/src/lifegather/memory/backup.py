"""Operator-only whole-database snapshot; never expose as a personal-data tool.

A snapshot is a JSON-lines file taken inside one consistent read transaction:

    {"format": ..., "migration": ..., "tables": [...]}     header
    {"table": name, "columns": [...], "rows": n}            one per table
    [value, ...]                                            n rows
    {"end": true}

Values are JSON scalars or lists; bytes and dates are tagged objects. Tables are
written in foreign-key order so a restore can insert them directly.
"""

import base64
import json
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import IO, Any

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Connection,
    Engine,
    Integer,
    MetaData,
    Table,
    func,
    inspect,
    select,
    text,
)

from lifegather.database import begin_snapshot

RowTransform = Callable[[str, dict[str, Any]], dict[str, Any]]

FORMAT = "lifegather-snapshot/1"
MAX_LINE_BYTES = 64 * 1024 * 1024
BATCH_ROWS = 200


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    table: str
    columns: tuple[str, ...]
    rows: int
    offset: int


def _encode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytes": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if value.keys() == {"bytes"} and isinstance(value["bytes"], str):
            return base64.b64decode(value["bytes"], validate=True)
        if value.keys() == {"date"} and isinstance(value["date"], str):
            return date.fromisoformat(value["date"])
        raise SnapshotError("Snapshot value has an unknown encoding")
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _line(output: IO[bytes], value: Any) -> None:
    output.write(
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
    )


def application_tables(connection: Connection) -> list[Table]:
    """Reflected tables in foreign-key order, excluding migration bookkeeping."""
    metadata = MetaData()
    metadata.reflect(connection)
    return [
        table for table in metadata.sorted_tables if table.name != "alembic_version"
    ]


def current_migration(connection: Connection) -> str:
    if not inspect(connection).has_table("alembic_version"):
        raise SnapshotError("The database has no schema version")
    revisions = list(
        connection.scalars(text("SELECT version_num FROM alembic_version LIMIT 2"))
    )
    if len(revisions) != 1:
        raise SnapshotError("The database schema version is ambiguous")
    return str(revisions[0])


def write_snapshot(
    connection: Connection, output: IO[bytes], transform: RowTransform | None = None
) -> dict[str, int]:
    """Write every table from the caller's open read snapshot.

    `transform` may rewrite one row at a time, for example to inline stored files.
    """
    tables = application_tables(connection)
    _line(
        output,
        {
            "format": FORMAT,
            "migration": current_migration(connection),
            "tables": [table.name for table in tables],
        },
    )
    counts: dict[str, int] = {}
    for table in tables:
        count = connection.scalar(select(func.count()).select_from(table)) or 0
        columns = [column.name for column in table.columns]
        _line(output, {"table": table.name, "columns": columns, "rows": count})
        order = list(table.primary_key.columns) or list(table.columns)
        written = 0
        result = connection.execution_options(yield_per=BATCH_ROWS).execute(
            select(*table.columns).order_by(*order)
        )
        for row in result:
            values = dict(row._mapping)
            if transform is not None:
                values = transform(table.name, values)
            _line(output, [_encode(values[name]) for name in columns])
            written += 1
        if written != count:
            raise SnapshotError("Snapshot rows changed while being written")
        counts[table.name] = count
    _line(output, {"end": True})
    return counts


def operator_snapshot(
    engine: Engine, destination: Path, transform: RowTransform | None = None
) -> dict[str, int]:
    """Consistent whole-database snapshot to a new protected file."""
    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as output, engine.connect() as connection:
            begin_snapshot(connection)
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            counts = write_snapshot(connection, output, transform)
            connection.rollback()
            output.flush()
            os.fsync(output.fileno())
        return counts
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


class SnapshotReader:
    """Random access to the sections of a snapshot file without loading it."""

    def __init__(self, source: IO[bytes]) -> None:
        self.source = source
        self.sections: dict[str, Section] = {}
        source.seek(0)
        header = self._json(self._readline())
        if (
            not isinstance(header, dict)
            or header.keys() != {"format", "migration", "tables"}
            or header["format"] != FORMAT
            or not isinstance(header["migration"], str)
            or not isinstance(header["tables"], list)
            or not all(isinstance(name, str) for name in header["tables"])
            or len(set(header["tables"])) != len(header["tables"])
        ):
            raise SnapshotError("Invalid snapshot header")
        self.migration: str = header["migration"]
        self.order: list[str] = header["tables"]
        for name in self.order:
            section = self._json(self._readline())
            if (
                not isinstance(section, dict)
                or section.keys() != {"table", "columns", "rows"}
                or section["table"] != name
                or not isinstance(section["columns"], list)
                or not all(isinstance(column, str) for column in section["columns"])
                or type(section["rows"]) is not int
                or section["rows"] < 0
            ):
                raise SnapshotError("Invalid snapshot table section")
            self.sections[name] = Section(
                name, tuple(section["columns"]), section["rows"], source.tell()
            )
            for _ in range(section["rows"]):
                self._readline()
        if self._json(self._readline()) != {"end": True} or source.read(1):
            raise SnapshotError("Snapshot is incomplete or has trailing data")

    def _readline(self) -> bytes:
        line = self.source.readline(MAX_LINE_BYTES + 1)
        if not line.endswith(b"\n") or len(line) > MAX_LINE_BYTES:
            raise SnapshotError("Snapshot is truncated or has an oversized row")
        return line

    @staticmethod
    def _json(line: bytes) -> Any:
        try:
            return json.loads(line)
        except (ValueError, RecursionError):
            raise SnapshotError("Snapshot contains invalid JSON") from None

    def rows(self, table: str) -> Iterator[dict[str, Any]]:
        section = self.sections.get(table)
        if section is None:
            raise SnapshotError("Snapshot is missing a required table")
        self.source.seek(section.offset)
        for _ in range(section.rows):
            values = self._json(self._readline())
            if not isinstance(values, list) or len(values) != len(section.columns):
                raise SnapshotError("Snapshot row does not match its table")
            yield dict(zip(section.columns, map(_decode, values), strict=True))


def _batches(
    rows: Iterable[dict[str, Any]], size: int = BATCH_ROWS
) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def migrate_to(connection: Connection, revision: str) -> None:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "migrations")
    )
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def require_empty(connection: Connection) -> None:
    if inspect(connection).get_table_names():
        raise SnapshotError("Restore requires an empty database")


def _parents_first(
    table: Table, rows: Iterable[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    """Order rows so self-referencing foreign keys point at inserted rows."""
    links = [
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
        if constraint.referred_table is table
    ]
    if not links:
        return rows
    pending = list(rows)
    inserted: set[tuple[tuple[str, ...], tuple[Any, ...]]] = set()
    ordered: list[dict[str, Any]] = []
    while pending:
        waiting = []
        for row in pending:
            references = [
                (target, tuple(row.get(name) for name in source))
                for source, target in links
            ]
            if all(
                None in values or (target, values) in inserted
                for target, values in references
            ):
                ordered.append(row)
                inserted.update(
                    (target, tuple(row.get(name) for name in target))
                    for _, target in links
                )
            else:
                waiting.append(row)
        if len(waiting) == len(pending):
            raise SnapshotError("Snapshot rows reference missing history")
        pending = waiting
    return ordered


def load_tables(
    connection: Connection,
    tables: list[Table],
    rows: Mapping[str, Iterable[dict[str, Any]]],
) -> dict[str, int]:
    """Insert rows into freshly migrated tables, then advance sequences."""
    counts: dict[str, int] = {}
    for table in tables:
        count = 0
        for batch in _batches(_parents_first(table, rows.get(table.name, ()))):
            if not set().union(*batch) <= set(table.columns.keys()):
                raise SnapshotError("Snapshot columns do not match the schema")
            connection.execute(table.insert(), batch)
            count += len(batch)
        counts[table.name] = count
    for table in tables:
        for column in table.primary_key.columns:
            if not isinstance(column.type, Integer):
                continue
            # Serial keys continue after the highest restored value.
            connection.execute(
                text(
                    "SELECT setval(sequence, COALESCE((SELECT max("
                    + connection.dialect.identifier_preparer.quote(column.name)
                    + ") FROM "
                    + connection.dialect.identifier_preparer.quote(table.name)
                    + "), 0) + 1, false) FROM (SELECT pg_get_serial_sequence("
                    ":table, :column) AS sequence) AS owned WHERE sequence IS NOT NULL"
                ),
                {"table": table.name, "column": column.name},
            )
    return counts


def restore_snapshot(source: IO[bytes], engine: Engine) -> dict[str, int]:
    """Load a snapshot into an empty database inside one transaction."""
    reader = SnapshotReader(source)
    with engine.begin() as connection:
        require_empty(connection)
        migrate_to(connection, reader.migration)
        tables = application_tables(connection)
        if [table.name for table in tables] != reader.order or any(
            reader.sections[table.name].columns != tuple(table.columns.keys())
            for table in tables
        ):
            raise SnapshotError("Snapshot tables do not match its schema version")
        counts = load_tables(
            connection, tables, {name: reader.rows(name) for name in reader.order}
        )
        if any(counts[name] != reader.sections[name].rows for name in reader.order):
            raise SnapshotError("Restored row counts do not match the snapshot")
        return counts
