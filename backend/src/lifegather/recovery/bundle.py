"""Encrypted operator bundles; restore only into an exclusive fresh directory."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from lifegather.config import Settings
from lifegather.credentials.service import read_key
from lifegather.installation_config import MAX_CONFIGURATION_BYTES, unique_object
from lifegather.memory.backup import operator_snapshot
from lifegather.recovery.configuration import (
    capture_configuration,
    encode_configuration,
    restored_configuration,
    validate_configuration,
)
from lifegather.recovery.database import (
    DatabaseSummary,
    connect_readonly,
    finalize_snapshot,
    validate_database,
)
from lifegather.recovery.envelope import (
    CHUNK_BYTES,
    MAX_PLAINTEXT_BYTES,
    RecoveryError,
    decrypt_file,
    encrypt_file,
)
from lifegather.version import __version__

MAX_MANIFEST_BYTES = 65536
PARTS = ("database.sqlite3", "configuration.json", "vault.key")
REQUIRED_PARTS = frozenset(PARTS[:2])


class FileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    format: Literal["lifegather-recovery/1"] = "lifegather-recovery/1"
    application_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    created_at: int = Field(ge=0)
    migration: str = Field(min_length=1, max_length=100)
    files: dict[str, FileRecord] = Field(min_length=2, max_length=3)


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
            self.manifest.files["database.sqlite3"].size,
            self.database,
        )


@contextmanager
def _exclusive_file(path: Path) -> Iterator[BinaryIO]:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
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
        source = self.settings.data_dir / "auth.sqlite3"
        if not source.is_file():
            raise RecoveryError("The configured installation database is missing")
        try:
            key = read_key(self.settings.vault_key_file)
            with self._staging() as staging:
                database = staging / "database.sqlite3"
                engine = create_engine(
                    "sqlite://",
                    creator=lambda: connect_readonly(source),
                    poolclass=NullPool,
                )
                try:
                    operator_snapshot(engine, database)
                finally:
                    engine.dispose()
                finalize_snapshot(database)
                summary = validate_database(database, key, standalone=True)
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
        except (OSError, ValueError, sqlite3.Error, SQLAlchemyError):
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
                if not REQUIRED_PARTS <= names or not names <= set(PARTS):
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
            database = staging / "database.sqlite3"
            summary = validate_database(database, key, standalone=True)
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

    def restore(self, bundle: Path, destination: Path, password: bytes) -> BundleInfo:
        try:
            return self._restore(bundle, destination, password)
        except RecoveryError:
            raise
        except (OSError, ValueError):
            raise RecoveryError("Unable to restore the installation") from None

    def _restore(self, bundle: Path, destination: Path, password: bytes) -> BundleInfo:
        target = self._destination(destination)
        with self._staging() as staging:
            verified = self._open(bundle, password, staging)
            configuration = restored_configuration(
                verified.configuration, target, verified.key is not None
            )
            target.mkdir(mode=0o700)
            created_files: list[Path] = []
            created_directories = [target]
            try:
                data = target / "data"
                data.mkdir(mode=0o700)
                created_directories.append(data)
                database = data / "auth.sqlite3"
                with (
                    verified.database_path.open("rb") as source,
                    _exclusive_file(database) as output,
                ):
                    _copy_part(
                        source, output, verified.manifest.files["database.sqlite3"]
                    )
                created_files.append(database)
                validate_database(database, verified.key, standalone=True)
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
