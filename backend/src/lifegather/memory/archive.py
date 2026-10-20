"""Bounded owner-only records/originals ZIP, never an installation backup."""

import hashlib
import json
import re
import secrets
import sqlite3
import stat
from collections.abc import Buffer
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import cast
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from sqlalchemy import Connection, Engine, Table, func, literal_column, select
from sqlalchemy.exc import SQLAlchemyError

from lifegather.auth.store import Account
from lifegather.documents.formats import MIMES
from lifegather.documents.models import Document
from lifegather.memory.export import EXCLUSIONS, FORMAT, ExportLimitError, RecordExport
from lifegather.photos.models import Photo
from lifegather.version import __version__

ARCHIVE_FORMAT = "lifegather-personal-archive/1"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ORIGINALS = 1000
CHUNK_BYTES = 1024 * 1024


class ArchiveError(ValueError):
    """Safe integrity/runtime error with no private filenames or content."""


class _BoundedBuffer(BytesIO):
    def write(self, value: Buffer, /) -> int:
        if self.tell() + memoryview(value).nbytes > MAX_ARCHIVE_BYTES:
            raise ExportLimitError("Personal archive exceeds the 64 MiB download limit")
        return super().write(value)


@dataclass(frozen=True)
class _Original:
    table: str
    category: str
    identifier: str
    rowid: int
    filename: str
    mime: str
    size: int
    digest: str

    @property
    def path(self) -> str:
        extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "application/pdf": "pdf",
        }.get(self.mime, "bin")
        extension = next(
            (key for key, mime in MIMES.items() if mime == self.mime), extension
        )
        return f"originals/{self.category}/{UUID(self.identifier).hex}.{extension}"


def _info(path: str, stamp: datetime) -> ZipInfo:
    item = ZipInfo(path, stamp.timetuple()[:6])
    item.create_system = 3
    item.external_attr = (stat.S_IFREG | 0o600) << 16
    item.compress_type = ZIP_STORED
    return item


def _originals(connection: Connection, actor: Account) -> list[_Original]:
    files: list[_Original] = []
    paths: set[str] = set()
    for model, category in ((Photo, "photos"), (Document, "documents")):
        table = cast(Table, model.__table__)
        columns = [
            literal_column(f"{table.name}.rowid").label("rowid"),
            table.c.id,
            table.c.filename,
            table.c.size,
            table.c.content_hash,
            func.length(table.c.original).label("stored_size"),
        ]
        if model is Photo:
            columns.append(table.c.mime)
        else:
            columns.append(table.c.format)
        rows = connection.execute(
            select(*columns)
            .where(table.c.user_id == actor.id, table.c.deleted_at.is_(None))
            .order_by(table.c.id)
            .limit(MAX_ORIGINALS - len(files) + 1)
        ).mappings()
        for row in rows:
            if len(files) >= MAX_ORIGINALS:
                raise ExportLimitError(
                    "Personal archive exceeds the 1,000-original limit"
                )
            if (
                row["stored_size"] is None
                or row["size"] <= 0
                or row["size"] != row["stored_size"]
                or not re.fullmatch(r"[a-f0-9]{64}", row["content_hash"])
            ):
                raise ArchiveError("Saved original evidence could not be verified")
            item = _Original(
                table.name,
                category,
                row["id"],
                row["rowid"],
                row["filename"],
                row["mime"] if model is Photo else MIMES[row["format"]],
                row["size"],
                row["content_hash"],
            )
            path = item.path  # Reject unsafe IDs and ambiguous paths before ZIP output.
            if path in paths:
                raise ArchiveError("Saved original identifiers could not be verified")
            paths.add(path)
            files.append(item)
    return files


class PersonalArchive:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def download(self, actor: Account) -> bytes:
        try:
            return self._download(actor)
        except (ArchiveError, ExportLimitError):
            raise
        except (
            ValueError,
            TypeError,
            sqlite3.Error,
            SQLAlchemyError,
            OSError,
            OverflowError,
        ):
            raise ArchiveError("Unable to prepare verified original evidence") from None

    def _download(self, actor: Account) -> bytes:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            stamp = datetime.now(UTC)
            records = RecordExport(self.engine).render_in(
                connection, actor, snapshot_at=stamp
            )
            files = _originals(connection, actor)
            if len(records) + sum(item.size for item in files) > MAX_ARCHIVE_BYTES:
                raise ExportLimitError(
                    "Personal archive exceeds the 64 MiB download limit"
                )
            driver = connection.connection.driver_connection
            if not isinstance(driver, sqlite3.Connection):
                raise ArchiveError("Original evidence archives require SQLite")
            manifest_files = []
            with _BoundedBuffer() as output:
                with ZipFile(
                    output, "w", compression=ZIP_STORED, allowZip64=False
                ) as archive:
                    archive.writestr(_info("records.json", stamp), records)
                    for item in files:
                        digest = hashlib.sha256()
                        count = 0
                        with (
                            driver.blobopen(
                                item.table, "original", item.rowid, readonly=True
                            ) as original,
                            archive.open(_info(item.path, stamp), "w") as target,
                        ):
                            while block := original.read(CHUNK_BYTES):
                                count += len(block)
                                if count > item.size or target.write(block) != len(
                                    block
                                ):
                                    raise ArchiveError(
                                        "Saved original evidence could not be verified"
                                    )
                                digest.update(block)
                        if count != item.size or not secrets.compare_digest(
                            digest.hexdigest(), item.digest
                        ):
                            raise ArchiveError(
                                "Saved original evidence could not be verified"
                            )
                        manifest_files.append(
                            {
                                "kind": item.category,
                                "id": item.identifier,
                                "path": item.path,
                                "original_filename": item.filename,
                                "mime": item.mime,
                                "size": item.size,
                                "sha256": item.digest,
                            }
                        )
                    manifest = {
                        "format": ARCHIVE_FORMAT,
                        "application_version": __version__,
                        "snapshot_at": stamp.isoformat(),
                        "purpose": "personal portability; not installation recovery",
                        "records_format": FORMAT,
                        "records": {
                            "path": "records.json",
                            "size": len(records),
                            "sha256": hashlib.sha256(records).hexdigest(),
                        },
                        "originals": manifest_files,
                        "excluded": [
                            *EXCLUSIONS[:2],
                            "photo previews and deleted/purged original files",
                            EXCLUSIONS[3],
                        ],
                    }
                    archive.writestr(
                        _info("manifest.json", stamp),
                        json.dumps(
                            manifest,
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                        ).encode("utf-8"),
                    )
                return output.getvalue()
