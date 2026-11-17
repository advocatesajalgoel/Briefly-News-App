"""Filesystem storage, served by the API at ``/media``.

Good enough for development and for a single-server deployment behind nginx.
Swap ``BRIEFLY_STORAGE_BACKEND=s3`` when you outgrow it — nothing else changes.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.storage.base import ObjectStorage, StoredObject


class LocalStorage(ObjectStorage):
    name = "local"

    def __init__(self, root: Path | None = None, public_base_url: str | None = None) -> None:
        settings = get_settings()
        self.root = Path(root) if root else settings.media_dir
        self.public_base_url = (public_base_url or settings.storage_public_base_url).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Never let a key escape the media root.
        safe = Path(key.lstrip("/")).as_posix().replace("..", "")
        path = (self.root / safe).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError(f"unsafe storage key: {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(
            key=key,
            url=f"{self.public_base_url}/{key.lstrip('/')}",
            size_bytes=len(data),
            content_type=content_type,
        )

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
