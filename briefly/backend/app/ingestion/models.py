"""Transport objects for ingestion — no database types here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawArticle:
    """One feed entry, normalised but not yet persisted."""

    source_slug: str
    source_name: str
    url: str
    canonical_url: str
    url_hash: str
    headline: str
    feed_summary: str = ""
    author: str | None = None
    guid: str | None = None
    published_at: datetime | None = None
    language: str = "en"
    discovery_channel: str = "publisher_feed"
    discovery_query: str | None = None
    # Publisher reported by an aggregator feed, when the aggregator is not the
    # publisher (Google News tells us who actually filed the story).
    reported_publisher: str | None = None
    reported_publisher_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class FetchResult:
    feed_url: str
    ok: bool
    status_code: int | None = None
    articles: list[RawArticle] = field(default_factory=list)
    error: str | None = None
    skipped_reason: str | None = None
    etag: str | None = None
    last_modified: str | None = None

    @property
    def count(self) -> int:
        return len(self.articles)
