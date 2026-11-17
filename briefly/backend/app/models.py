"""SQLAlchemy models — the single shared story database.

The news cards and the podcast are two renderings of the *same* rows:
``Story`` + ``ExtractedFact`` + ``StorySource``. Nothing in the podcast path
reads from a separate pipeline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import (
    EpisodeKind,
    FactKind,
    FactSlot,
    ProcessingStatus,
    SourceAccess,
    SourceKind,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


class Category(Base, TimestampMixin):
    """A news section. New categories are rows, not code changes."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Lower numbers sort first in the app's category rail.
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Keywords used by the rule-based classifier when a feed gives no section.
    keywords: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # A synthetic category (e.g. "for-you") is assembled at read time.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    stories: Mapped[list[Story]] = relationship(back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Category {self.slug}>"


class Source(Base, TimestampMixin):
    """A publisher we ingest from, plus the terms we must honour for it."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    feed_url: Mapped[str | None] = mapped_column(Text)
    # Domains that identify this publisher when an aggregator links to it.
    domains: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    kind: Mapped[str] = mapped_column(String(24), default=SourceKind.OTHER, nullable=False)
    access: Mapped[str] = mapped_column(
        String(24), default=SourceAccess.FEED_HEADLINE, nullable=False
    )
    country: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(12), default="en", nullable=False)
    # True for publishers that operate their own reporting desk. Aggregators and
    # syndication-only outlets are False and do not add to the independent count.
    is_independent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Politeness controls
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Conditional-GET hints from the last fetch: {"etag": ..., "last_modified": ...}
    feed_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    articles: Mapped[list[Article]] = relationship(back_populates="source")

    __table_args__ = (Index("ix_sources_enabled_kind", "is_enabled", "kind"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source {self.slug}>"


# ---------------------------------------------------------------------------
# Ingested material
# ---------------------------------------------------------------------------


class Article(Base, TimestampMixin):
    """One item as it appeared in one publisher's feed.

    We store the publisher's own headline, the short feed summary the publisher
    chose to syndicate, and the canonical URL. We never store a scraped copy of
    the full article body.
    """

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL")
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    guid: Mapped[str | None] = mapped_column(Text)

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    # Short syndicated blurb straight from the feed. Bounded on write.
    feed_summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(12), default="en", nullable=False)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Where we found it: "publisher_feed" or "google_news".
    discovery_channel: Mapped[str] = mapped_column(String(32), default="publisher_feed")
    discovery_query: Mapped[str | None] = mapped_column(String(160))
    raw: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(
        String(24), default=ProcessingStatus.PENDING, nullable=False
    )
    # Lexical fingerprint used by the clusterer (token -> tf-idf weight).
    fingerprint: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list | None] = mapped_column(JSONB)

    source: Mapped[Source] = relationship(back_populates="articles")
    story: Mapped[Story | None] = relationship(back_populates="articles")

    __table_args__ = (
        UniqueConstraint("source_id", "url_hash", name="uq_articles_source_url"),
        Index("ix_articles_status_published", "status", "published_at"),
        Index("ix_articles_story", "story_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Article {self.headline[:40]!r}>"


# ---------------------------------------------------------------------------
# The story: one event, many sources
# ---------------------------------------------------------------------------


class Story(Base, TimestampMixin):
    """A cluster of articles that all report the same event."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )

    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    # The card headline: the plainest of the outlets' own headlines.
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    # The card summary. `summary_word_count` is written by the word budget and
    # the check constraint below makes an over-length summary unstorable.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Whose words the card is in. "composed" is Briefly's own summary, written
    # from extracted facts. "excerpt" is one outlet's own opening line, quoted
    # unaltered and credited by name on the card — what Briefly shows when there
    # is no model to write an original summary, because the alternative would be
    # passing a publisher's sentence off as its own.
    summary_kind: Mapped[str] = mapped_column(
        String(16), default="composed", server_default="composed", nullable=False
    )
    wording_source_name: Mapped[str | None] = mapped_column(String(160))
    # Longer neutral brief used by the Deep Dive narrator (still original prose).
    dek: Mapped[str | None] = mapped_column(Text)

    first_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Diversity indicator — a count of *where reporting came from*, not a bias score.
    diversity_level: Mapped[str] = mapped_column(String(12), default="low", nullable=False)
    diversity_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    has_official_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_disputed_claims: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default="reported", nullable=False)

    rank_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    rank_components: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(
        String(24), default=ProcessingStatus.PENDING, nullable=False, index=True
    )
    qc_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # Centroid of member articles; kept so new articles can join an open cluster.
    centroid: Mapped[dict | None] = mapped_column(JSONB)
    entity_keys: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    category: Mapped[Category | None] = relationship(back_populates="stories")
    articles: Mapped[list[Article]] = relationship(back_populates="story")
    story_sources: Mapped[list[StorySource]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    facts: Mapped[list[ExtractedFact]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    podcast_entries: Mapped[list[PodcastStory]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("summary_word_count >= 0", name="ck_stories_wordcount_nonneg"),
        CheckConstraint("summary_word_count <= 30", name="ck_stories_summary_max_30_words"),
        CheckConstraint(
            "summary_kind IN ('composed', 'excerpt')", name="ck_stories_summary_kind"
        ),
        CheckConstraint(
            "summary_kind <> 'excerpt' OR wording_source_name IS NOT NULL OR summary = ''",
            name="ck_stories_excerpt_is_credited",
        ),
        Index("ix_stories_status_rank", "status", "rank_score"),
        Index("ix_stories_category_published", "category_id", "published_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Story {self.headline[:48]!r} sources={self.source_count}>"


class StorySource(Base, TimestampMixin):
    """The transparency row: which publisher reported this, when, and where.

    One per (story, source). Holds the publisher's *own* headline and the link,
    so the app can show the user exactly who said what and send them there.
    """

    __tablename__ = "story_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL")
    )

    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    original_headline: Mapped[str] = mapped_column(Text, nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    similarity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    story: Mapped[Story] = relationship(back_populates="story_sources")
    source: Mapped[Source] = relationship()

    __table_args__ = (
        UniqueConstraint("story_id", "source_id", name="uq_story_sources_story_source"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StorySource {self.source_name}>"


class ExtractedFact(Base, TimestampMixin):
    """A single structured fact pulled out of the cluster before any prose exists.

    The 30-word card and the podcast script are both written *from these rows*.
    Every fact carries the source it came from so nothing can be asserted
    without a traceable origin.
    """

    __tablename__ = "extracted_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )

    slot: Mapped[str] = mapped_column(String(16), default=FactSlot.OTHER, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default=FactKind.ATTRIBUTED, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Who is credited with saying it, when the fact is attributed.
    attributed_to: Mapped[str | None] = mapped_column(Text)
    # Verbatim snippet from the feed blurb that supports this fact. Short, and
    # only ever used for verification — never rendered to the user as content.
    evidence: Mapped[str | None] = mapped_column(Text)
    # How many independent sources carry this fact.
    support_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    salience: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    story: Mapped[Story] = relationship(back_populates="facts")

    __table_args__ = (
        Index("ix_facts_story_slot", "story_id", "slot"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_facts_confidence_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Fact {self.slot}:{self.kind} {self.text[:32]!r}>"


# ---------------------------------------------------------------------------
# People and their saved things
# ---------------------------------------------------------------------------


class User(Base, TimestampMixin):
    """A reader.

    v1 of the app stores bookmarks on-device and needs no account. A device
    installs itself here anonymously (``device_id``) so the same bookmarks can
    follow the reader later without a rewrite.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    preferred_categories: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    locale: Mapped[str] = mapped_column(String(12), default="en-IN", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.device_id[:12]}>"


class Bookmark(Base, TimestampMixin):
    __tablename__ = "bookmarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="bookmarks")
    story: Mapped[Story] = relationship(back_populates="bookmarks")

    __table_args__ = (UniqueConstraint("user_id", "story_id", name="uq_bookmarks_user_story"),)


# ---------------------------------------------------------------------------
# Podcast — same story rows, different rendering
# ---------------------------------------------------------------------------


class PodcastEpisode(Base, TimestampMixin):
    __tablename__ = "podcast_episodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), default=EpisodeKind.DAILY, nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    # The date the episode covers (its editorial date, not its creation time).
    edition_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    script: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Ordered segments with their own text + the story they came from.
    script_segments: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    script_word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    audio_url: Mapped[str | None] = mapped_column(Text)
    audio_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    audio_bytes: Mapped[int | None] = mapped_column(Integer)
    audio_mime_type: Mapped[str | None] = mapped_column(String(64))
    tts_provider: Mapped[str | None] = mapped_column(String(32))
    tts_voice: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(
        String(24), default=ProcessingStatus.PENDING, nullable=False, index=True
    )
    qc_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    entries: Mapped[list[PodcastStory]] = relationship(
        back_populates="episode", cascade="all, delete-orphan", order_by="PodcastStory.position"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Episode {self.kind} {self.slug}>"


class PodcastStory(Base, TimestampMixin):
    """Join row: which story appears where in an episode, and its narration."""

    __tablename__ = "podcast_stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("podcast_episodes.id", ondelete="CASCADE"), nullable=False
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    segment_title: Mapped[str | None] = mapped_column(Text)
    narration: Mapped[str] = mapped_column(Text, default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_offset_seconds: Mapped[int | None] = mapped_column(Integer)

    episode: Mapped[PodcastEpisode] = relationship(back_populates="entries")
    story: Mapped[Story] = relationship(back_populates="podcast_entries")

    __table_args__ = (
        UniqueConstraint("episode_id", "story_id", name="uq_podcast_stories_episode_story"),
        Index("ix_podcast_stories_episode_pos", "episode_id", "position"),
    )


class PipelineRun(Base, TimestampMixin):
    """Audit trail for automated runs — what ran, what it produced, what failed."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=ProcessingStatus.PROCESSING)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
