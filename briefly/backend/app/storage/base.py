from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StoredObject:
    key: str
    url: str
    size_bytes: int
    content_type: str


class ObjectStorage:
    name = "base"

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:  # pragma: no cover
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # pragma: no cover
        raise NotImplementedError
