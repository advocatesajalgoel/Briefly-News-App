"""Ingestion service: fetch feeds, credit the right publisher, persist articles."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import ProcessingStatus, SourceAccess, SourceKind
from app.ingestion import google_news
from app.ingestion.fetcher import FeedFetcher, FeedState
from app.ingestion.models import RawArticle
from app.ingestion.registry import discovery_queries, feed_plan, source_for_domain
from app.models import Article, Source
from app.text.article_form import REPORT, article_form
from app.text.normalize import canonical_url, clean_text, registered_domain, tokenize

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _strip_publisher_suffix(headline: str, publisher_name: str) -> str:
    """Aggregators append " - Publisher Name"; that is not part of the headline."""
    if not headline:
        return ""
    suffix = f" - {publisher_name}"
    if headline.endswith(suffix):
        return headline[: -len(suffix)]
    return re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", headline)


def slugify(value: str, max_len: int = 64) -> str:
    slug = _SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return slug[:max_len] or "source"


@dataclass
class IngestStats:
    feeds_attempted: int = 0
    feeds_ok: int = 0
    feeds_skipped: int = 0
    feeds_failed: int = 0
    articles_seen: int = 0
    articles_created: int = 0
    articles_duplicate: int = 0
    articles_stale: int = 0
    # Live pages, videos, opinion, explainers, galleries: real items, but not
    # reports of an event, so they never become cards. Counted, not hidden.
    articles_not_reports: int = 0
    not_report_forms: dict = field(default_factory=dict)
    sources_created: int = 0
    errors: list[str] = field(default_factory=list)
    # One line per feed polled: who, which URL, what happened. This is the
    # first thing to read when a section looks thin.
    feeds: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "feeds_attempted": self.feeds_attempted,
            "feeds_ok": self.feeds_ok,
            "feeds_skipped": self.feeds_skipped,
            "feeds_failed": self.feeds_failed,
            "articles_seen": self.articles_seen,
            "articles_created": self.articles_created,
            "articles_duplicate": self.articles_duplicate,
            "articles_stale": self.articles_stale,
            "articles_not_reports": self.articles_not_reports,
            "not_report_forms": dict(self.not_report_forms),
            "sources_created": self.sources_created,
            "errors": self.errors[:20],
            "feeds": self.feeds,
        }


class IngestionService:
    def __init__(self, db: Session, fetcher: FeedFetcher | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self._fetcher = fetcher
        self._owns_fetcher = fetcher is None
        self.stats = IngestStats()
        # Reports filed by this run that the database cannot see yet. The
        # session does not autoflush, so a query for "do we already hold this
        # URL?" misses anything added since the last flush — and real feeds do
        # list the same link twice in one document.
        self._filed: dict[tuple[object, str], Article] = {}

    @property
    def fetcher(self) -> FeedFetcher:
        if self._fetcher is None:
            self._fetcher = FeedFetcher()
        return self._fetcher

    def close(self) -> None:
        if self._owns_fetcher and self._fetcher is not None:
            self._fetcher.close()
            self._fetcher = None

    # -- publisher resolution --------------------------------------------
    def _resolve_publisher(self, raw: RawArticle, feed_source: Source) -> Source:
        """Work out who actually filed the story.

        For a publisher's own feed that is the feed owner. For an aggregator we
        use the publisher the aggregator credits, matching first on the article
        domain, then on the credited name, and finally creating a new source row
        so the reader still sees a real publisher rather than "Google News".
        """
        if feed_source.kind != SourceKind.AGGREGATOR:
            return feed_source

        domain = registered_domain(raw.url)
        if domain and "google" not in domain:
            match = source_for_domain(self.db, domain)
            if match:
                return match

        if raw.reported_publisher_url:
            match = source_for_domain(self.db, registered_domain(raw.reported_publisher_url))
            if match:
                return match

        name = clean_text(raw.reported_publisher or "")
        if not name:
            return feed_source

        slug = slugify(name)
        existing = self.db.scalar(select(Source).where(Source.slug == slug))
        if existing:
            return existing

        pub_domain = registered_domain(raw.reported_publisher_url or "") or None
        created = Source(
            slug=slug,
            name=name,
            homepage_url=raw.reported_publisher_url,
            feed_url=None,
            domains=[pub_domain] if pub_domain else [],
            kind=SourceKind.OTHER,
            access=SourceAccess.FEED_HEADLINE,
            language=raw.language or "en",
            is_independent=True,
            is_enabled=True,
            notes="Auto-created from an aggregator credit. Review kind/country before it "
                  "counts toward source diversity.",
        )
        self.db.add(created)
        self.db.flush()
        self.stats.sources_created += 1
        return created

    # -- persistence ------------------------------------------------------
    def _persist(self, raw: RawArticle, publisher: Source, feed_source: Source) -> Article | None:
        cutoff = datetime.now(UTC) - timedelta(hours=self.settings.ingest_lookback_hours)
        if raw.published_at and raw.published_at < cutoff:
            self.stats.articles_stale += 1
            return None

        form = article_form(raw.headline, raw.canonical_url or raw.url)
        if form != REPORT:
            self.stats.articles_not_reports += 1
            self.stats.not_report_forms[form] = self.stats.not_report_forms.get(form, 0) + 1
            return None

        existing = self.db.scalar(
            select(Article).where(
                Article.source_id == publisher.id, Article.url_hash == raw.url_hash
            )
        )
        if existing is None:
            existing = self._filed.get((publisher.id, raw.url_hash))
        if existing is None:
            # An aggregator links to its own redirect, so the URL differs even
            # though the story is one we already hold from the same publisher.
            existing = self._same_report_from_publisher(raw, publisher)
        if existing is not None:
            self.stats.articles_duplicate += 1
            # An aggregator hit confirms a story we already have; keep the
            # earliest publication time we have seen for it.
            if raw.published_at and (
                existing.published_at is None or raw.published_at < existing.published_at
            ):
                existing.published_at = raw.published_at
            # The same report often arrives twice — once in a publisher's front
            # page feed and again in its business feed. Keep the filing.
            # Only the publisher's own filing counts here: an aggregator's
            # topic page is a much looser label than a publisher's desk.
            hint = raw.discovery_query or ""
            if (
                raw.discovery_channel == "publisher_feed"
                and hint.startswith("topic:")
                and not (existing.discovery_query or "").startswith("topic:")
            ):
                existing.discovery_query = hint
            return None

        # A restricted publisher's words are not stored — link only.
        summary = raw.feed_summary
        if publisher.access == SourceAccess.RESTRICTED:
            summary = ""

        article = Article(
            source_id=publisher.id,
            url=raw.url,
            canonical_url=raw.canonical_url or canonical_url(raw.url),
            url_hash=raw.url_hash,
            guid=raw.guid,
            headline=raw.headline,
            feed_summary=summary or None,
            author=raw.author,
            language=raw.language or publisher.language,
            published_at=raw.published_at or datetime.now(UTC),
            discovery_channel=raw.discovery_channel,
            discovery_query=raw.discovery_query,
            raw={
                **raw.raw,
                "credited_via": feed_source.slug,
                "credited_publisher": raw.reported_publisher,
            },
            status=ProcessingStatus.PENDING,
        )
        self.db.add(article)
        self._filed[(publisher.id, raw.url_hash)] = article
        self.stats.articles_created += 1
        return article

    def _same_report_from_publisher(self, raw: RawArticle, publisher: Source) -> Article | None:
        """Has this publisher already given us this report under another URL?"""
        window_start = (raw.published_at or datetime.now(UTC)) - timedelta(hours=12)
        window_end = (raw.published_at or datetime.now(UTC)) + timedelta(hours=12)
        candidates = self.db.scalars(
            select(Article).where(
                Article.source_id == publisher.id,
                Article.published_at >= window_start,
                Article.published_at <= window_end,
            )
        ).all()
        incoming = set(tokenize(_strip_publisher_suffix(raw.headline, publisher.name)))
        if not incoming:
            return None
        for candidate in candidates:
            known = set(tokenize(_strip_publisher_suffix(candidate.headline, publisher.name)))
            if not known:
                continue
            if len(incoming & known) / min(len(incoming), len(known)) >= 0.85:
                return candidate
        return None

    # -- feed runners -----------------------------------------------------
    def ingest_feed(
        self,
        feed_url: str,
        feed_source: Source,
        *,
        discovery_channel: str = "publisher_feed",
        discovery_query: str | None = None,
    ) -> list[Article]:
        self.stats.feeds_attempted += 1
        cached = feed_source.feed_state or {}
        state = FeedState(
            etag=cached.get(feed_url, {}).get("etag"),
            last_modified=cached.get(feed_url, {}).get("last_modified"),
        )
        result = self.fetcher.fetch(
            feed_url,
            source_slug=feed_source.slug,
            source_name=feed_source.name,
            state=state,
            discovery_channel=discovery_channel,
            discovery_query=discovery_query,
        )
        feed_source.last_fetched_at = datetime.now(UTC)

        report = {"source": feed_source.slug, "url": feed_url, "channel": discovery_channel, "query": discovery_query, "status": "ok", "items": 0}
        self.stats.feeds.append(report)

        if not result.ok:
            if result.skipped_reason:
                self.stats.feeds_skipped += 1
                report.update(status="skipped", detail=result.skipped_reason)
            else:
                self.stats.feeds_failed += 1
                feed_source.consecutive_failures += 1
                feed_source.last_error = result.error
                self.stats.errors.append(f"{feed_source.slug}: {result.error}")
                report.update(status="failed", detail=result.error)
            return []

        self.stats.feeds_ok += 1
        report["items"] = len(result.articles)
        feed_source.consecutive_failures = 0
        feed_source.last_error = None
        if result.etag or result.last_modified:
            new_state = dict(cached)
            new_state[feed_url] = {
                "etag": result.etag,
                "last_modified": result.last_modified,
            }
            feed_source.feed_state = new_state

        # One feed's rows go in under a savepoint. Live feeds are the least
        # predictable input this system has; a row the database refuses should
        # cost that one feed, not the whole day's edition.
        created: list[Article] = []
        counted = (self.stats.articles_created, dict(self._filed))
        try:
            with self.db.begin_nested():
                for raw in result.articles:
                    self.stats.articles_seen += 1
                    publisher = self._resolve_publisher(raw, feed_source)
                    article = self._persist(raw, publisher, feed_source)
                    if article is not None:
                        created.append(article)
                self.db.flush()
        except SQLAlchemyError as exc:
            self.stats.articles_created, self._filed = counted
            self.stats.feeds_ok -= 1
            self.stats.feeds_failed += 1
            detail = f"database refused this feed's rows: {type(exc).__name__}"
            self.stats.errors.append(f"{feed_source.slug}: {detail}")
            report.update(status="failed", detail=detail, items=0)
            logger.warning("feed %s rolled back: %s", feed_url, str(exc).splitlines()[0][:200])
            return []
        return created

    def ingest_publisher_feeds(self) -> list[Article]:
        sources = self.db.scalars(
            select(Source).where(
                Source.is_enabled.is_(True),
                Source.feed_url.is_not(None),
                Source.kind != SourceKind.AGGREGATOR,
            )
        ).all()
        plan = feed_plan()
        out: list[Article] = []
        for source in sources:
            if source.access == SourceAccess.RESTRICTED:
                continue
            feeds = plan.get(source.slug) or [(source.feed_url, None)]
            for url, category in feeds:
                out.extend(
                    self.ingest_feed(
                        url,
                        source,
                        discovery_query=f"topic:{category}" if category else None,
                    )
                )
        return out

    def ingest_google_news(self) -> list[Article]:
        aggregator = self.db.scalar(select(Source).where(Source.slug == "google-news"))
        if aggregator is None or not aggregator.is_enabled:
            return []

        out: list[Article] = []
        for category_slug, feed_url in google_news.default_discovery_feeds():
            out.extend(
                self.ingest_feed(
                    feed_url,
                    aggregator,
                    discovery_channel="google_news",
                    discovery_query=f"topic:{category_slug}",
                )
            )
        for entry in discovery_queries():
            url = google_news.search_feed_url(entry["query"], when=entry.get("when", "1d"))
            out.extend(
                self.ingest_feed(
                    url,
                    aggregator,
                    discovery_channel="google_news",
                    discovery_query=f"topic:{entry['category']}" if entry.get("category") else entry["query"],
                )
            )
        return out

    def ingest_all(self) -> IngestStats:
        try:
            self.ingest_google_news()
            self.ingest_publisher_feeds()
        finally:
            self.close()
        return self.stats
