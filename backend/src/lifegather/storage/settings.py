"""Build the configured storage backend."""

from typing import TYPE_CHECKING

from lifegather.storage.base import ObjectStorage, StorageError
from lifegather.storage.local import LocalStorage
from lifegather.storage.s3 import S3Storage

if TYPE_CHECKING:
    from lifegather.config import Settings


def storage_from_settings(settings: "Settings") -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.files_dir)
    try:
        import boto3  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        raise StorageError(
            "S3 storage needs the optional 's3' extra (boto3) installed"
        ) from None
    secret = settings.s3_secret_access_key.get_secret_value()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region or None,
        # Empty values fall back to boto3's standard credential chain.
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=secret or None,
    )
    return S3Storage(client, settings.s3_bucket, settings.s3_prefix)
