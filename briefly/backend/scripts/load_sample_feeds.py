#!/usr/bin/env python3
"""Populate a database from the fictional sample feeds in data/sample_feeds.

Use this to bring the app up end-to-end without touching the network: the feeds
go through the real ingestion, clustering, extraction, summarisation, ranking and
quality-control code — only the HTTP fetch is swapped for reading a file.

The stories are invented, so the outlets are too: every item is filed under an
outlet that does not exist (see scripts/sample_identity.py) before the pipeline
reads it. No real publisher is ever shown — or heard — reporting a sample story.

    python -m scripts.load_sample_feeds            # ingest + cluster + process
    python -m scripts.load_sample_feeds --podcast  # also build and voice episodes
    python -m scripts.load_sample_feeds --reset    # wipe stories/articles first
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.ingestion.fetcher import FeedFetcher  # noqa: E402
from app.ingestion.models import FetchResult  # noqa: E402
from app.ingestion.parser import parse_feed_bytes  # noqa: E402
from app.ingestion.registry import sync_categories, sync_sources  # noqa: E402
from app.ingestion.service import IngestionService  # noqa: E402
from app.models import (  # noqa: E402
    Article,
    Bookmark,
    ExtractedFact,
    PodcastEpisode,
    PodcastStory,
    Source,
    Story,
    StorySource,
)
from app.pipeline import orchestrator  # noqa: E402
from app.podcast import service as podcast_service  # noqa: E402
from scripts.sample_identity import SAMPLE_AGGREGATOR_FEED, SampleIdentity  # noqa: E402

# Shipped data, not a test artefact: this script runs in production — it is
# what the publishing workflow falls back to on a day when no feed answers —
# so the feeds it reads belong beside the source registry, not under tests/.
FIXTURES = Path(__file__).resolve().parent.parent / "data" / "sample_feeds"

# The instant the newest fixture item should appear to have been published.
FIXTURE_NEWEST_AGE = timedelta(minutes=20)

# All fixtures share one editorial "now" so the shift is the same across feeds
# and the relative spacing between outlets — which clustering depends on — is
# preserved exactly.
FIXTURE_EPOCH = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)


def _shift_to_recent(articles):
    """Move fixture timestamps forward so the batch reads as today's news."""
    offset = (datetime.now(UTC) - FIXTURE_NEWEST_AGE) - FIXTURE_EPOCH
    for article in articles:
        if article.published_at is not None:
            article.published_at = article.published_at + offset
    return articles


class FileFetcher(FeedFetcher):
    """A FeedFetcher that reads from disk. Same parsing, no network.

    Timestamps in the fixtures are shifted forward so the newest item lands a few
    minutes ago, preserving the spacing between them. Without this the sample
    data would work only in the week it was written: the ingester correctly
    discards anything older than ``BRIEFLY_INGEST_LOOKBACK_HOURS``, so a fixed
    date means a new checkout ingests nothing and the whole demo looks broken.
    """

    def __init__(  # noqa: D107
        self,
        directory: Path = FIXTURES,
        *,
        freshen: bool = True,
        identity: SampleIdentity | None = None,
    ) -> None:
        self.directory = directory
        self.freshen = freshen
        # When set, every item is re-filed under an invented outlet before the
        # pipeline sees it. The test suite leaves this off on purpose.
        self.identity = identity
        self._owns_client = False
        self.client = None  # type: ignore[assignment]
        self._last_request_at = {}

    def close(self) -> None:
        return None

    def fetch(self, feed_url: str, *, source_slug: str, source_name: str, state=None,
              discovery_channel="publisher_feed", discovery_query=None, limit=None) -> FetchResult:
        fixture = self.identity.fixture_slug(source_slug) if self.identity else source_slug
        path = self.directory / f"{fixture}.xml"
        if not path.exists():
            return FetchResult(feed_url=feed_url, ok=False,
                               skipped_reason=f"no sample feed for {source_slug}")
        articles = parse_feed_bytes(
            path.read_bytes(),
            source_slug=source_slug,
            source_name=source_name,
            discovery_channel=discovery_channel,
            discovery_query=discovery_query,
            limit=limit or 60,
        )
        if self.freshen:
            articles = _shift_to_recent(articles)
        if self.identity:
            articles = [self.identity.rewrite(a) for a in articles]
        return FetchResult(feed_url=feed_url, ok=True, status_code=200, articles=articles)


def reset(db) -> None:
    db.execute(delete(PodcastStory))
    db.execute(delete(PodcastEpisode))
    db.execute(delete(Bookmark))
    db.execute(delete(ExtractedFact))
    db.execute(delete(StorySource))
    db.execute(delete(Article))
    db.execute(delete(Story))
    db.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--podcast", action="store_true")
    parser.add_argument("--no-voice", action="store_true")
    args = parser.parse_args()

    out: dict = {}
    with session_scope() as db:
        sync_categories(db)
        sync_sources(db)
        if args.reset:
            reset(db)

        identity = SampleIdentity(db)
        service = IngestionService(db, fetcher=FileFetcher(identity=identity))
        registry = db.scalars(
            select(Source).where(Source.feed_url.is_not(None), Source.is_enabled.is_(True))
        ).all()
        # Every invented outlet exists before anything is ingested, so that the
        # aggregator's credits below resolve to them and never to a real row.
        outlets = [o for o in (identity.outlet_for(real) for real in registry) if o]
        for outlet in outlets:
            service.ingest_feed(outlet.feed_url, outlet.source)
        # And the aggregator path, which credits publishers rather than itself.
        aggregator = db.scalar(select(Source).where(Source.slug == "google-news"))
        if aggregator is not None:
            service.ingest_feed(
                SAMPLE_AGGREGATOR_FEED,
                aggregator,
                discovery_channel="google_news",
                discovery_query="topic:india",
            )
        out["ingest"] = service.stats.as_dict()

        out["clustering"] = orchestrator.run_clustering(db)
        out["processing"] = orchestrator.run_processing(db)

        if args.podcast:
            daily = podcast_service.generate_daily_episode(db)
            if daily is not None:
                if not args.no_voice and daily.status != "flagged":
                    podcast_service.synthesise_episode(db, daily)
                out["daily"] = {
                    "slug": daily.slug, "status": daily.status,
                    "stories": len(daily.entries), "words": daily.script_word_count,
                    "seconds": daily.audio_duration_seconds or daily.estimated_duration_seconds,
                    "audio_url": daily.audio_url,
                    "qc_passed": (daily.qc_report or {}).get("passed"),
                }
            deep = podcast_service.generate_deep_dive_episode(db)
            if deep is not None:
                if not args.no_voice and deep.status != "flagged":
                    podcast_service.synthesise_episode(db, deep)
                out["deep_dive"] = {
                    "slug": deep.slug, "status": deep.status,
                    "words": deep.script_word_count,
                    "audio_url": deep.audio_url,
                    "qc_passed": (deep.qc_report or {}).get("passed"),
                }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
