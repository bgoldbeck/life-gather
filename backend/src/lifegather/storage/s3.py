"""Private S3-compatible bucket storage (AWS S3, MinIO, Backblaze B2, R2, ...)."""

from typing import Any, Protocol

from lifegather.storage.base import ObjectNotFound, StorageError, validate_key

MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3Client(Protocol):
    """The subset of a boto3 S3 client that the backend uses."""

    def put_object(self, **kwargs: Any) -> Any: ...
    def get_object(self, **kwargs: Any) -> Any: ...
    def delete_object(self, **kwargs: Any) -> Any: ...
    def head_object(self, **kwargs: Any) -> Any: ...


def _missing(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    return str(response.get("Error", {}).get("Code", "")) in MISSING_CODES


class S3Storage:
    def __init__(
        self,
        client: S3Client,
        bucket: str,
        prefix: str = "",
        account_quota_bytes: int = 0,
    ) -> None:
        if not bucket:
            raise StorageError("Configure an S3 bucket")
        self.client = client
        self.bucket = bucket
        self.account_quota_bytes = account_quota_bytes
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    def _key(self, key: str) -> str:
        return self.prefix + validate_key(key)

    def save(self, data: bytes, key: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(key),
                Body=data,
                ContentType="application/octet-stream",
            )
        except StorageError:
            raise
        except Exception:
            raise StorageError("Unable to save the stored file") from None

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            body = response["Body"]
            try:
                data = body.read()
            finally:
                body.close()
        except StorageError:
            raise
        except Exception as error:
            if _missing(error):
                raise ObjectNotFound("Stored file is missing") from None
            raise StorageError("Unable to read the stored file") from None
        if not isinstance(data, bytes):
            raise StorageError("Unable to read the stored file")
        return data

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
        except StorageError:
            raise
        except Exception as error:
            if not _missing(error):
                raise StorageError("Unable to delete the stored file") from None

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except StorageError:
            raise
        except Exception as error:
            if _missing(error):
                return False
            raise StorageError("Unable to check the stored file") from None
        return True
