"""S3 / S3-compatible storage (AWS, Cloudflare R2, MinIO, Wasabi, ...)."""

from __future__ import annotations

from app.config import get_settings
from app.storage.base import ObjectStorage, StoredObject


class S3Storage(ObjectStorage):
    name = "s3"

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "BRIEFLY_STORAGE_BACKEND=s3 needs the optional dependency: "
                "pip install 'briefly-backend[s3]'"
            ) from exc

        settings = get_settings()
        if not settings.s3_bucket:
            raise RuntimeError("BRIEFLY_S3_BUCKET must be set when using the s3 backend")

        self.settings = settings
        self.bucket = settings.s3_bucket
        kwargs = {"region_name": settings.aws_region or None}
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        # No credentials in kwargs => boto3 uses the instance role, which is the
        # preferred production setup.
        self.client = boto3.client("s3", **kwargs)

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        key = key.lstrip("/")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=86400",
        )
        base = self.settings.storage_public_base_url.rstrip("/")
        return StoredObject(key=key, url=f"{base}/{key}", size_bytes=len(data),
                            content_type=content_type)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key.lstrip("/"))

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key.lstrip("/"))
            return True
        except ClientError:
            return False
