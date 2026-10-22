"""Encrypted operator bundles; restore only into a fresh directory and database."""

import hashlib
import json
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from lifegather.config import Settings
from lifegather.credentials.service import read_keyring
from lifegather.database import create_database_engine
from lifegather.installation_config import MAX_CONFIGURATION_BYTES, unique_object
from lifegather.legacy_import import LegacyImportError, check_legacy, import_legacy
from lifegather.memory.backup import SnapshotError, operator_snapshot, restore_snapshot
from lifegather.recovery.configuration import (
    capture_configuration,
    encode_configuration,
    restored_configuration,
    validate_configuration,
)
from lifegather.recovery.database import (
    DatabaseSummary,
    inline_stored_objects,
    validate_database,
    validate_snapshot,
)
from lifegather.recovery.envelope import (
    CHUNK_BYTES,
    MAX_PLAINTEXT_BYTES,
    RecoveryError,
    decrypt_file,
    encrypt_file,
)
from lifegather.storage.base import StorageError
from lifegather.storage.settings import storage_from_settings
from lifegather.version import __version__

MAX_MANIFEST_BYTES = 65536
FORMAT: Final = "lifegather-recovery/2"
# Format 1 bundles carry a SQLite database from releases before PostgreSQL.
LEGACY_FORMAT: Final = "lifegather-recovery/1"
DATABASE_PARTS = {FORMAT: "database.jsonl", LEGACY_FORMAT: "database.sqlite3"}
PARTS = ("database.jsonl", "database.sqlite3", "configuration.json", "vault.key")


class FileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    format: Literal["lifegather-recovery/1", "lifegather-recovery/2"] = FORMAT
    application_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    created_at: int = Field(ge=0)
    migration: str = Field(min_length=1, max_length=100)
    files: dict[str, FileRecord] = Field(min_length=2, max_length=3)

    @property
    def database_part(self) -> str:
        return DATABASE_PARTS[self.format]

    @property
    def parts(self) -> frozenset[str]:
        return frozenset({self.database_part, "configuration.json", "vault.key"})


@dataclass(frozen=True)
class BundleInfo:
    application_version: str
    revision: str | None
    created_at: int
    database_bytes: int
    database: DatabaseSummary


@dataclass(frozen=True)
class _Verified:
    manifest: Manifest
    database: DatabaseSummary
    database_path: Path
    configuration: dict[str, Any] = field(repr=False)
    key: bytes | None = field(repr=False)

    def info(self) -> BundleInfo:
        return BundleInfo(
            self.manifest.application_version,
            self.manifest.revision,
            self.manifest.created_at,
            self.manifest.files[self.manifest.database_part].size,
            self.database,
        )


@contextmanager
def _exclusive_file(path: Path) -> Iterator[BinaryIO]:
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            yield output
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_bytes(path: Path, value: bytes) -> None:
    with _exclusive_file(path) as output:
        if output.write(value) != len(value):
            raise RecoveryError("Unable to write complete recovery data")


def _record(path: Path) -> FileRecord:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as source:
        while block := source.read(CHUNK_BYTES):
            digest.update(block)
            count += len(block)
    return FileRecord(size=count, sha256=digest.hexdigest())


def _copy_part(source: BinaryIO, output: BinaryIO, expected: FileRecord) -> None:
    remaining = expected.size
    digest = hashlib.sha256()
    while remaining:
        block = source.read(min(CHUNK_BYTES, remaining))
        if not block:
            raise RecoveryError("Recovery payload is incomplete")
        remaining -= len(block)
        digest.update(block)
        if output.write(block) != len(block):
            raise RecoveryError("Unable to write complete recovery data")
    if not secrets.compare_digest(digest.hexdigest(), expected.sha256):
        raise RecoveryError("Recovery payload hash does not match its manifest")


class RecoveryService:
    def __init__(self, settings: Settings, *, staging_dir: Path | None = None) -> None:
        self.settings = settings
        self.staging_dir = staging_dir

    def _private(self, path: Path) -> None:
        if self.settings.static_dir is not None and path.resolve().is_relative_to(
            self.settings.static_dir.resolve()
        ):
            raise RecoveryError("Keep recovery files outside the static directory")

    @contextmanager
    def _staging(self) -> Iterator[Path]:
        parent = self.staging_dir
        if parent is None and self.settings.data_dir.is_dir():
            parent = self.settings.data_dir
        if parent is not None:
            self._private(parent)
        with TemporaryDirectory(prefix="lifegather-recovery-", dir=parent) as name:
            path = Path(name)
            self._private(path)
            yield path

    def _destination(self, path: Path) -> Path:
        # Resolve parents, but never follow/overwrite an existing final symlink.
        target = path.parent.resolve() / path.name
        self._private(target)
        if target.exists() or target.is_symlink():
            raise RecoveryError("Choose a new recovery destination")
        return target

    def create(self, destination: Path, password: bytes) -> BundleInfo:
        target = self._destination(destination)
        try:
            # The active key; a pending rotation fails the bundle's key check.
            keyring = read_keyring(self.settings)
            key = keyring.active if keyring is not None else None
            engine = create_database_engine(self.settings.database())
            with self._staging() as staging:
                database = staging / "database.jsonl"
                try:
                    operator_snapshot(
                        engine,
                        database,
                        inline_stored_objects(storage_from_settings(self.settings)),
                    )
                except StorageError:
                    raise RecoveryError(
                        "A stored original is missing or does not match"
                    ) from None
                finally:
                    engine.dispose()
                summary = validate_snapshot(database, key)
                config_path = staging / "configuration.json"
                _write_bytes(
                    config_path,
                    encode_configuration(capture_configuration(self.settings)),
                )
                configuration = validate_configuration(
                    config_path, staging, key is not None
                )
                if key is not None:
                    _write_bytes(staging / "vault.key", key)
                files = {
                    name: _record(staging / name)
                    for name in PARTS
                    if (staging / name).is_file()
                }
                manifest = Manifest(
                    format=FORMAT,
                    application_version=__version__,
                    revision=self.settings.build_revision or None,
                    created_at=time.time_ns() // 1000,
                    migration=summary.migration,
                    files=files,
                )
                raw_manifest = manifest.model_dump_json().encode("utf-8")
                if len(raw_manifest) > MAX_MANIFEST_BYTES:
                    raise RecoveryError("Recovery manifest exceeds its limit")
                if (
                    4
                    + len(raw_manifest)
                    + sum(record.size for record in files.values())
                    > MAX_PLAINTEXT_BYTES
                ):
                    raise RecoveryError(
                        "Recovery payload exceeds the format size limit"
                    )
                payload = staging / "payload.bin"
                with _exclusive_file(payload) as output:
                    output.write(len(raw_manifest).to_bytes(4, "big"))
                    output.write(raw_manifest)
                    for name in PARTS:
                        if name not in files:
                            continue
                        with (staging / name).open("rb") as part:
                            _copy_part(part, output, files[name])
                            if part.read(1):
                                raise RecoveryError("Staged recovery data changed")
                with _exclusive_file(target) as output:
                    encrypt_file(payload, output, password)
                return _Verified(manifest, summary, database, configuration, key).info()
        except RecoveryError:
            raise
        except (OSError, ValueError, SQLAlchemyError, StorageError):
            raise RecoveryError(
                "Unable to create the encrypted recovery bundle"
            ) from None

    def _open(self, bundle: Path, password: bytes, staging: Path) -> _Verified:
        payload = staging / "payload.bin"
        decrypt_file(bundle, payload, password)
        try:
            with payload.open("rb") as source:
                prefix = source.read(4)
                if (
                    len(prefix) != 4
                    or not 1 <= int.from_bytes(prefix, "big") <= MAX_MANIFEST_BYTES
                ):
                    raise RecoveryError("Invalid recovery manifest length")
                length = int.from_bytes(prefix, "big")
                raw = source.read(length)
                manifest = Manifest.model_validate(
                    json.loads(raw, object_pairs_hook=unique_object)
                )
                names = set(manifest.files)
                required = {manifest.database_part, "configuration.json"}
                if not required <= names or not names <= manifest.parts:
                    raise RecoveryError("Unexpected recovery payload members")
                if "vault.key" in names and manifest.files["vault.key"].size != 32:
                    raise RecoveryError("Invalid recovery vault key")
                if manifest.files["configuration.json"].size > MAX_CONFIGURATION_BYTES:
                    raise RecoveryError("Recovery configuration exceeds its limit")
                expected_size = (
                    4 + length + sum(record.size for record in manifest.files.values())
                )
                if os.fstat(source.fileno()).st_size != expected_size:
                    raise RecoveryError(
                        "Recovery payload length does not match its manifest"
                    )
                for name in PARTS:
                    if name in names:
                        with _exclusive_file(staging / name) as output:
                            _copy_part(source, output, manifest.files[name])
                if source.read(1):
                    raise RecoveryError("Unexpected trailing recovery payload")
            key = (staging / "vault.key").read_bytes() if "vault.key" in names else None
            configuration = validate_configuration(
                staging / "configuration.json", staging, key is not None
            )
            database = staging / manifest.database_part
            if manifest.format == LEGACY_FORMAT:
                summary = _legacy_summary(database)
            else:
                summary = validate_snapshot(database, key)
            if summary.migration != manifest.migration:
                raise RecoveryError("Recovery migration does not match its manifest")
            return _Verified(manifest, summary, database, configuration, key)
        except RecoveryError:
            raise
        except (OSError, ValueError, TypeError, RecursionError):
            raise RecoveryError("Unable to validate the recovery bundle") from None

    def verify(self, bundle: Path, password: bytes) -> BundleInfo:
        try:
            with self._staging() as staging:
                return self._open(bundle, password, staging).info()
        except RecoveryError:
            raise
        except (OSError, ValueError):
            raise RecoveryError("Unable to verify the recovery bundle") from None

    def restore(
        self, bundle: Path, destination: Path, password: bytes, database_url: str
    ) -> BundleInfo:
        try:
            return self._restore(bundle, destination, password, database_url)
        except RecoveryError:
            raise
        except (OSError, ValueError, SnapshotError, SQLAlchemyError):
            raise RecoveryError("Unable to restore the installation") from None

    def _restore(
        self, bundle: Path, destination: Path, password: bytes, database_url: str
    ) -> BundleInfo:
        target = self._destination(destination)
        engine = create_database_engine(database_url)
        try:
            with self._staging() as staging:
                verified = self._open(bundle, password, staging)
                configuration = restored_configuration(
                    verified.configuration,
                    target,
                    verified.key is not None,
                    engine.url.render_as_string(hide_password=False),
                )
                target.mkdir(mode=0o700)
                created_files: list[Path] = []
                created_directories = [target]
                try:
                    data = target / "data"
                    data.mkdir(mode=0o700)
                    created_directories.append(data)
                    if verified.manifest.format == LEGACY_FORMAT:
                        try:
                            if import_legacy(verified.database_path, engine) is None:
                                raise RecoveryError(
                                    "Restore requires an empty PostgreSQL database"
                                )
                        except LegacyImportError as error:
                            raise RecoveryError(str(error)) from None
                    else:
                        with verified.database_path.open("rb") as source:
                            try:
                                restore_snapshot(source, engine)
                            except SnapshotError as error:
                                raise RecoveryError(str(error)) from None
                    validate_database(engine, verified.key)
                    if verified.key is not None:
                        secret_directory = target / "secrets"
                        secret_directory.mkdir(mode=0o700)
                        created_directories.append(secret_directory)
                        key_path = secret_directory / "vault.key"
                        _write_bytes(key_path, verified.key)
                        created_files.append(key_path)
                    config_path = target / "installation.json"
                    _write_bytes(config_path, configuration)
                    created_files.append(config_path)
                    return verified.info()
                except BaseException:
                    for path in reversed(created_files):
                        with suppress(OSError):
                            path.unlink()
                    for path in reversed(created_directories):
                        with suppress(OSError):
                            path.rmdir()
                    raise
        finally:
            engine.dispose()


def _legacy_summary(path: Path) -> DatabaseSummary:
    """Format 1 bundles are checked for integrity; restore validates fully."""
    try:
        migration, counts = check_legacy(path)
    except LegacyImportError as error:
        raise RecoveryError(str(error)) from None
    return DatabaseSummary(migration=migration, **counts)
