"""Private files in a local (Docker-mounted) directory."""

import os
from pathlib import Path

from lifegather.storage.base import ObjectNotFound, StorageError, validate_key

# Windows has no O_NOFOLLOW (symlinks are refused explicitly there) and needs
# O_BINARY so the C runtime never translates line endings in stored bytes.
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
BINARY = getattr(os, "O_BINARY", 0)


class LocalStorage:
    def __init__(self, root: Path, account_quota_bytes: int = 0) -> None:
        self.root = root
        self.account_quota_bytes = account_quota_bytes

    def _path(self, key: str) -> Path:
        validate_key(key)
        root = self.root.resolve()
        path = root.joinpath(*key.split("/"))
        # The key pattern already forbids traversal; also refuse symlinked parents.
        if not path.parent.resolve().is_relative_to(root):
            raise StorageError("Storage path escapes its directory")
        return path

    def save(self, data: bytes, key: str) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self._path(key)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            if not NOFOLLOW and temporary.is_symlink():
                raise StorageError("Storage path is a symbolic link")
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_TRUNC | os.O_WRONLY | NOFOLLOW | BINARY,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        except OSError:
            raise StorageError("Unable to save the stored file") from None

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not NOFOLLOW and path.is_symlink():
            raise StorageError("Unable to read the stored file")
        try:
            descriptor = os.open(path, os.O_RDONLY | NOFOLLOW | BINARY)
        except FileNotFoundError:
            raise ObjectNotFound("Stored file is missing") from None
        except OSError:
            raise StorageError("Unable to read the stored file") from None
        try:
            with os.fdopen(descriptor, "rb") as source:
                return source.read()
        except OSError:
            raise StorageError("Unable to read the stored file") from None

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            raise StorageError("Unable to delete the stored file") from None

    def exists(self, key: str) -> bool:
        path = self._path(key)
        return path.is_file() and not path.is_symlink()
