"""Restore one personal archive ZIP into an account, all or nothing.

The archive is untrusted input: every member, hash, field and type is checked
before anything is written, and IDs are kept so citations and history still
point at the same records. Records the account already holds are left exactly as
they are; only missing records are added. Only portable SQLAlchemy Core
statements are used.
"""

import hashlib
import json
import secrets
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any, Literal, cast
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import (
    Boolean,
    Date,
    Engine,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
    tuple_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import sort_tables

from lifegather.auth.store import Account
from lifegather.database import account_scope
from lifegather.documents.formats import MIMES
from lifegather.memory.archive import (
    MAX_ARCHIVE_BYTES,
    MAX_ORIGINALS,
    original_path,
)
from lifegather.memory.export import (
    COLLECTIONS,
    FORMAT,
    MAX_BYTES,
    MAX_RECORDS,
    PREVIOUS_FORMATS,
)
from lifegather.memory.models import Alias, Entity, Episode
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import decode
from lifegather.storage.base import ObjectStorage, StorageError
from lifegather.storage.originals import delete_quietly, object_key
from lifegather.storage.quota import describe_limit, has_room

MAX_MANIFEST_BYTES = 1024 * 1024
TABLES = {projection.table.name: projection for projection in COLLECTIONS}
# Parents before children; rows that point at their own table are ordered below.
ORDER = [table.name for table in sort_tables([p.table for p in COLLECTIONS])]
ID_BATCH = 500
# Plain names for the natural-key clash message.
LABELS = {
    "asset_types": "asset type",
    "memory_sources": "source or memory",
    "documents": "document",
    "photos": "photo",
}


class RestoreError(ValueError):
    """The upload is not a complete, unmodified, supported personal archive."""


class RestoreLimitError(RestoreError):
    """The upload exceeds the fixed archive limits."""


class RestoreConflict(ValueError):
    """The archive is valid, but this account or installation cannot take it."""


class _Records(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: Literal["records.json"]
    size: int = Field(ge=1, le=MAX_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class _Original(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["photos", "documents"]
    id: str = Field(min_length=1, max_length=36)
    path: str = Field(max_length=128)
    original_filename: str = Field(max_length=2400)
    mime: str = Field(max_length=200)
    size: int = Field(ge=1, le=MAX_ARCHIVE_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class _Manifest(BaseModel):
    # Descriptive keys (version, purpose, exclusions) are informational only.
    model_config = ConfigDict(extra="ignore", strict=True)

    format: Literal["lifegather-personal-archive/1"]
    records_format: Literal[
        "lifegather-records/4", "lifegather-records/5", "lifegather-records/6"
    ]
    snapshot_at: str = Field(max_length=64)
    records: _Records
    originals: list[_Original] = Field(max_length=MAX_ORIGINALS)


@dataclass(frozen=True)
class _Package:
    snapshot_at: str
    rows: dict[str, list[dict[str, Any]]]
    originals: dict[str, bytes]


def _reject_constant(value: str) -> Any:
    raise ValueError("Non-finite numbers are not accepted")


def _json(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)


def _member(package: ZipFile, info: ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise RestoreLimitError("Archive member exceeds its size limit")
    with package.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) != info.file_size:
        raise RestoreError("Archive member length does not match")
    return data


def _value(table: Table, name: str, value: Any) -> Any:
    column = table.c[name]
    if value is None:
        if not column.nullable:
            raise RestoreError("Archive record is missing a required value")
        return None
    kind = column.type
    if isinstance(kind, Boolean):
        if type(value) is not bool:
            raise RestoreError("Archive record has an invalid value")
    elif isinstance(kind, Integer):
        if type(value) is not int:
            raise RestoreError("Archive record has an invalid value")
    elif isinstance(kind, Date):
        if not isinstance(value, str) or len(value) != 10:
            raise RestoreError("Archive record has an invalid date")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise RestoreError("Archive record has an invalid date")
        return parsed
    elif isinstance(kind, String):
        if not isinstance(value, str):
            raise RestoreError("Archive record has an invalid value")
    else:  # pragma: no cover - the frozen projections only use these types
        raise RestoreError("Archive record has an unsupported value")
    return value


def _collections(records: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(records, dict) or (
        records.get("format") != FORMAT
        and records.get("format") not in PREVIOUS_FORMATS
    ):
        raise RestoreError(
            "Only lifegather-records/4, /5 and /6 archives can be restored"
        )
    collections = records.get("collections")
    absent = PREVIOUS_FORMATS.get(records["format"], frozenset())
    if not isinstance(collections, dict) or absent & set(collections):
        raise RestoreError("Archive records do not match the supported format")
    # Collections added after an older format are restored empty.
    collections = {**{name: [] for name in absent}, **collections}
    if len(collections) != len(TABLES) or set(collections) != set(TABLES):
        raise RestoreError("Archive records do not match the supported format")
    result: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for name, projection in TABLES.items():
        table = projection.table
        fields = projection.fields.split()
        rows = collections[name]
        if not isinstance(rows, list):
            raise RestoreError("Archive records do not match the supported format")
        total += len(rows)
        if total > MAX_RECORDS:
            raise RestoreLimitError("Archive has more than 10,000 records")
        prepared = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(fields):
                raise RestoreError("Archive record fields do not match the format")
            if name == "documents" and row["pages"] is None and row["format"] != "pdf":
                # The export omits the legacy page column for non-PDF formats;
                # uploads store 1 there and it is never displayed.
                row = row | {"pages": 1}
            value = {field: _value(table, field, row[field]) for field in fields}
            if not isinstance(value["id"], str) or not value["id"]:
                raise RestoreError("Archive record has an invalid identifier")
            prepared.append(value)
        if len({row["id"] for row in prepared}) != len(prepared):
            raise RestoreError("Archive records repeat an identifier")
        result[name] = prepared
    counts = records.get("counts")
    listed = {name: len(rows) for name, rows in result.items() if name not in absent}
    if counts != listed or records.get("total_records") != sum(
        len(rows) for rows in result.values()
    ):
        raise RestoreError("Archive record counts do not match")
    return result


def _expected_originals(
    rows: dict[str, list[dict[str, Any]]],
) -> dict[str, tuple[str, dict[str, Any], str]]:
    expected: dict[str, tuple[str, dict[str, Any], str]] = {}
    for kind in ("photos", "documents"):
        for row in rows[kind]:
            if row["deleted_at"] is not None:
                continue
            mime = row["mime"] if kind == "photos" else MIMES.get(row["format"])
            if mime is None or row["id"] in expected:
                raise RestoreError("Archive file records do not match the format")
            expected[row["id"]] = (kind, row, mime)
    return expected


def read_archive(raw: bytes) -> _Package:
    """Parse and verify everything before any database or storage write."""
    if not raw:
        raise RestoreError("Choose a personal archive ZIP")
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise RestoreLimitError("Archive exceeds the 64 MiB limit")
    try:
        with ZipFile(BytesIO(raw)) as package:
            return _read(package)
    except RestoreError:
        raise
    except (
        BadZipFile,
        ValidationError,
        UnicodeDecodeError,
        zlib.error,
        EOFError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        NotImplementedError,
        RuntimeError,
    ):
        raise RestoreError(
            "This file is not a valid, unmodified personal archive"
        ) from None


def _read(package: ZipFile) -> _Package:
    infos = package.infolist()
    if len(infos) > MAX_ORIGINALS + 2:
        raise RestoreLimitError("Archive has more than 1,000 originals")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise RestoreError("Archive repeats a file name")
    if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
        raise RestoreLimitError("Archive exceeds the 64 MiB limit")
    for info in infos:
        if (
            info.is_dir()
            or info.flag_bits & 0x1
            or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
        ):
            raise RestoreError("Archive contains an unsupported member")
    members = {info.filename: info for info in infos}
    manifest = _Manifest.model_validate(
        _json(_member(package, members["manifest.json"], MAX_MANIFEST_BYTES))
    )
    records_raw = _member(package, members["records.json"], MAX_BYTES)
    if len(records_raw) != manifest.records.size or not secrets.compare_digest(
        hashlib.sha256(records_raw).hexdigest(), manifest.records.sha256
    ):
        raise RestoreError("Archive records do not match the manifest")
    records = _json(records_raw)
    if (
        not isinstance(records, dict)
        or records.get("snapshot_at") != manifest.snapshot_at
        or records.get("format") != manifest.records_format
    ):
        raise RestoreError("Archive records do not match the manifest")
    rows = _collections(records)
    expected = _expected_originals(rows)
    listed = {entry.id: entry for entry in manifest.originals}
    if len(listed) != len(manifest.originals) or set(listed) != set(expected):
        raise RestoreError("Archive originals do not match the saved file records")
    if set(members) != {"manifest.json", "records.json"} | {
        entry.path for entry in manifest.originals
    }:
        raise RestoreError("Archive members do not match the manifest")
    originals: dict[str, bytes] = {}
    for identifier, (kind, row, mime) in expected.items():
        entry = listed[identifier]
        if (
            entry.kind != kind
            or entry.mime != mime
            or entry.path != original_path(kind, identifier, mime)
            or entry.size != row["size"]
            or entry.sha256 != row["content_hash"]
            or entry.original_filename != row["filename"]
        ):
            raise RestoreError("Archive originals do not match the saved file records")
        data = _member(package, members[entry.path], entry.size)
        if not secrets.compare_digest(hashlib.sha256(data).hexdigest(), entry.sha256):
            raise RestoreError("Archive original does not match its hash")
        originals[identifier] = data
    return _Package(manifest.snapshot_at, rows, originals)


def _self_ordered(table: Table, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order rows so earlier revisions precede rows that point back at them."""
    columns = sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table is table
            and key.column.name == "id"
            and key.parent.name != "id"
        }
    )
    if not columns:
        return rows
    present = {row["id"] for row in rows}
    waiting = {
        row["id"]: {
            row[c] for c in columns if row[c] in present and row[c] != row["id"]
        }
        for row in rows
    }
    by_id = {row["id"]: row for row in rows}
    ordered: list[dict[str, Any]] = []
    done: set[str] = set()
    while waiting:
        ready = sorted(key for key, needs in waiting.items() if needs <= done)
        if not ready:
            raise RestoreError("Archive history contains a cycle")
        for key in ready:
            ordered.append(by_id[key])
            done.add(key)
            del waiting[key]
    return ordered


def _chunks(values: list[str]) -> Iterable[list[str]]:
    for start in range(0, len(values), ID_BATCH):
        yield values[start : start + ID_BATCH]


class PersonalRestore:
    def __init__(self, engine: Engine, storage: ObjectStorage | None) -> None:
        self.engine = engine
        self.storage = storage
        self.memory = MemoryService(engine)

    def restore(self, actor: Account, raw: bytes) -> dict[str, Any]:
        package = read_archive(raw)
        storage = self.storage
        if storage is None:
            raise RestoreError("File storage is not configured")
        previews = {}
        for row in package.rows["photos"]:
            if row["id"] in package.originals:
                try:
                    decoded = decode(package.originals[row["id"]])
                except MemoryError:
                    raise RestoreError("Archive photo could not be read") from None
                if (decoded.mime, decoded.width, decoded.height) != (
                    row["mime"],
                    row["width"],
                    row["height"],
                ):
                    raise RestoreError("Archive photo does not match its record")
                previews[row["id"]] = decoded.preview
        self._check_foreign(actor, package)
        saved: list[str] = []
        try:
            with self.memory._write() as db:
                present = self._check_target(db, actor, package)
                merging = any(present.values()) or self._has_records(db, actor)
                added = {
                    name: [row for row in rows if row["id"] not in present[name]]
                    for name, rows in package.rows.items()
                }
                self._check_clashes(db, actor, added)
                rows = self._prepare(actor, added, package.originals, previews)
                new_ids = {
                    row["id"] for name in ("photos", "documents") for row in added[name]
                }
                incoming = sum(
                    len(data) + len(previews.get(identifier, b""))
                    for identifier, data in package.originals.items()
                    if identifier in new_ids
                )
                if not has_room(db, actor.id, storage, incoming):
                    raise RestoreConflict(
                        "This archive's files would take your account past its "
                        f"storage limit ({describe_limit(storage)}), so nothing "
                        "was restored."
                    )
                for identifier, data in package.originals.items():
                    if identifier not in new_ids:
                        # Never touch the files of a record the account already has.
                        continue
                    kind = "photos" if identifier in previews else "documents"
                    parts = [("original", data)]
                    if kind == "photos":
                        parts.append(("preview", previews[identifier]))
                    for part, content in parts:
                        key = object_key(actor.id, kind, identifier, part)
                        storage.save(content, key)
                        saved.append(key)
                try:
                    for name in ORDER:
                        if rows[name]:
                            db.execute(insert(TABLES[name].table), rows[name])
                    db.flush()
                except IntegrityError:
                    if merging:
                        raise RestoreConflict(
                            "Some records in this archive clash with different "
                            "versions already in your account, so nothing was "
                            "restored."
                        ) from None
                    raise RestoreError(
                        "Archive records are inconsistent and were not restored"
                    ) from None
                self._reindex(db, actor, added)
                self.memory._audit(
                    db,
                    actor,
                    "personal_archive_restored",
                    package.snapshot_at,
                    self.memory.clock(),
                )
        except StorageError:
            delete_quietly(storage, saved)
            raise RestoreError("Unable to store the restored originals") from None
        except BaseException:
            delete_quietly(storage, saved)
            raise
        counts = {name: len(added[name]) for name in TABLES}
        total = sum(counts.values())
        return {
            "snapshot_at": package.snapshot_at,
            "counts": counts,
            "total_records": total,
            "already_present": sum(len(rows) for rows in package.rows.values()) - total,
            "originals": sum(1 for key in saved if key.endswith("/original")),
        }

    @staticmethod
    def _has_records(db: Session, actor: Account) -> bool:
        return any(
            db.scalar(
                select(p.table.c.id).where(p.table.c.user_id == actor.id).limit(1)
            )
            for p in COLLECTIONS
        )

    def _check_foreign(self, actor: Account, package: _Package) -> None:
        """Refuse archive IDs held by another account in this installation.

        Row security hides other accounts' rows from the acting account, so only
        this existence check runs in the system context; nothing else is read.
        """
        with account_scope(None), Session(self.memory.engine) as db:
            for name, rows in package.rows.items():
                table = TABLES[name].table
                for chunk in _chunks([row["id"] for row in rows]):
                    if db.scalar(
                        select(table.c.id)
                        .where(table.c.id.in_(chunk), table.c.user_id != actor.id)
                        .limit(1)
                    ):
                        raise RestoreConflict(
                            "Records in this archive belong to another account in "
                            "this installation, for example the account it was "
                            "downloaded from."
                        )

    @staticmethod
    def _check_target(
        db: Session, actor: Account, package: _Package
    ) -> dict[str, set[str]]:
        """Return the archive IDs this account already holds."""
        present: dict[str, set[str]] = {}
        for name, rows in package.rows.items():
            table = TABLES[name].table
            present[name] = set()
            for chunk in _chunks([row["id"] for row in rows]):
                present[name].update(
                    db.scalars(
                        select(table.c.id).where(
                            table.c.user_id == actor.id, table.c.id.in_(chunk)
                        )
                    )
                )
        return present

    @staticmethod
    def _check_clashes(
        db: Session, actor: Account, added: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Refuse new records that repeat a different saved record's natural key.

        IDs are never rewritten, so two distinct records with the same source,
        request or starter key cannot both be kept. Partial unique indexes (one
        current history head) are left to the database and still roll back.
        """
        for name, rows in added.items():
            if not rows:
                continue
            table = TABLES[name].table
            keys = [
                [c.name for c in item.columns if c.name != "user_id"]
                for item in (*table.constraints, *table.indexes)
                if isinstance(item, (UniqueConstraint, Index))
                and (isinstance(item, UniqueConstraint) or item.unique)
                and not (
                    isinstance(item, Index)
                    and item.dialect_options["postgresql"]["where"] is not None
                )
                and "user_id" in item.columns
                and "id" not in item.columns
            ]
            for columns in keys:
                values = list(
                    {
                        tuple(row[c] for c in columns)
                        for row in rows
                        if all(row[c] is not None for c in columns)
                    }
                )
                key = tuple_(*(table.c[c] for c in columns))
                for start in range(0, len(values), ID_BATCH):
                    if db.scalar(
                        select(table.c.id)
                        .where(
                            table.c.user_id == actor.id,
                            key.in_(values[start : start + ID_BATCH]),
                        )
                        .limit(1)
                    ):
                        raise RestoreConflict(
                            f"A {LABELS.get(name, 'record')} in this archive "
                            "repeats a different one already in your account, so "
                            "nothing was restored. Records are never merged or "
                            "given new IDs."
                        )

    @staticmethod
    def _prepare(
        actor: Account,
        added: dict[str, list[dict[str, Any]]],
        originals: dict[str, bytes],
        previews: dict[str, bytes],
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for name, rows in added.items():
            table = TABLES[name].table
            prepared = []
            for row in _self_ordered(table, rows):
                value = {**row, "user_id": actor.id}
                if name == "photos":
                    active = row["id"] in previews
                    value |= {
                        "original": None,
                        "preview": None,
                        "original_key": object_key(
                            actor.id, "photos", row["id"], "original"
                        )
                        if active
                        else None,
                        "preview_key": object_key(
                            actor.id, "photos", row["id"], "preview"
                        )
                        if active
                        else None,
                    }
                    if active:
                        value["preview_size"] = len(previews[row["id"]])
                elif name == "documents":
                    active = row["id"] in originals
                    value |= {
                        "original": None,
                        "original_key": object_key(
                            actor.id, "documents", row["id"], "original"
                        )
                        if active
                        else None,
                    }
                prepared.append(value)
            result[name] = prepared
        return result

    def _reindex(
        self, db: Session, actor: Account, added: dict[str, list[dict[str, Any]]]
    ) -> None:
        for row in added[cast(Table, Episode.__table__).name]:
            self.memory._index(db, actor, row["id"], "source", row["text"])
        # A new alias on an entity the account already had refreshes that entity.
        entities = {row["id"] for row in added[cast(Table, Entity.__table__).name]}
        entities |= {
            row["entity_id"] for row in added[cast(Table, Alias.__table__).name]
        }
        for chunk in _chunks(sorted(entities)):
            names: dict[str, list[str]] = {}
            for entity_id, alias in db.execute(
                select(Alias.entity_id, Alias.name)
                .where(Alias.user_id == actor.id, Alias.entity_id.in_(chunk))
                .order_by(Alias.recorded_at, Alias.id)
            ):
                names.setdefault(entity_id, []).append(alias)
            for identifier, name in db.execute(
                select(Entity.id, Entity.name).where(
                    Entity.user_id == actor.id, Entity.id.in_(chunk)
                )
            ):
                body = name + "".join(
                    "\n" + alias for alias in names.get(identifier, [])
                )
                self.memory._index(db, actor, identifier, "entity", body)
