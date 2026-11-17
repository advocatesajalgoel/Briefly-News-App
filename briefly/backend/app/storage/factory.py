from __future__ import annotations

from app.config import get_settings
from app.storage.base import ObjectStorage
from app.storage.local import LocalStorage


def get_storage(name: str | None = None) -> ObjectStorage:
    backend = (name or get_settings().storage_backend or "local").lower()
    if backend == "local":
        return LocalStorage()
    if backend == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage()
    raise ValueError(f"unknown BRIEFLY_STORAGE_BACKEND {backend!r}; expected local or s3")
