"""Private object storage for original files, independent of where bytes live."""

from lifegather.storage.base import (
    ObjectNotFound,
    ObjectStorage,
    StorageError,
    validate_key,
)
from lifegather.storage.local import LocalStorage
from lifegather.storage.s3 import S3Storage
from lifegather.storage.settings import storage_from_settings

__all__ = [
    "LocalStorage",
    "ObjectNotFound",
    "ObjectStorage",
    "S3Storage",
    "StorageError",
    "storage_from_settings",
    "validate_key",
]
