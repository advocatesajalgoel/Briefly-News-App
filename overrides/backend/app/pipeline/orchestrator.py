"""End-to-end pipeline over the database.

    ingest -> cluster -> extract facts -> summarise -> rank -> quality control

Each stage is separately callable (the admin API exposes them individually) and
``run_full`` chains them. Every run is recorded in ``pipeline_runs``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.enums import ProcessingStatus, SourceKind
from app.llm.schema import SourceDocument
from app.models import (
    Article,
    Category,
    ExtractedFact,
    PipelineRun,
    Story,
    StorySource,
)
from app.pipeline.categorise import categorise
from app.pipeline.clustering import Cluster, build_items, cluster_items
from app.pipeline.diversity import SourceFacet, compute_diversity, describe
from app.pipeline.facts import extract_facts
from app.pipeline.qc import check_story
from app.pipeline.ranking import RankingInput, rank_story
from app.pipeline.summarize import build_summary
from app.pipeline.wording import choose_wording
from app.text.wordcount import count_words

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def story_slug(headline: str, when: datetime) -> str:
    base = _SLUG_RE.sub("-", (headline or "story").lower()).strip("-")[:120]
    return f"{when:%Y%m%d}-{base or 'story'}-{uuid.uuid4().hex[:6]}"


@dataclass
class StageStats:
    name: str
    processed: int = 0
    created: int = 0
    updated: int = 0
    flagged: int = 0
    published: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "stage": self.name,
            "processed": self.processed,
            "created": self.created,
            "updated": self.updated,
            "flagged": self.flagged,
            "published": self.published,
            "skipped": self.skipped,
            "errors": self.errors[:20],
        }


# ---------------------------------------------------------------------------
# Stage 1 — ingestion
# ---------------------------------------------------------------------------


def run_ingest(db: Session) -> dict:
    from app.ingestion.service import IngestionService

    service = IngestionService(db)
    stats = service.ingest_all()
    db.flush()
    return stats.as_dict()


# ---------------------------------------------------------------------------
# Stage 2 — clustering
# ---------------------------------------------------------------------------


def _documents_for(story: Story) -> list[SourceDocument]:
    docs: list[SourceDocument] = []
    for index, article in enumerate(sorted(story.articles, key=lambda a: a.published_at or datetime.max.replace(tzinfo=UTC))):
        docs.append(
            SourceDocument(
                index=index,
                source_slug=article.source.slug,
                source_name=article.source.name,
                source_kind=article.source.kind,
                headline=article.headline,
                summary=article.feed_summary or "",
                url=article.canonical_url,
                published_at=article.published_at.isoformat() if article.published_at else None,
            )
        )
    return docs


def _best_article_per_source(articles: list[Article]) -> dict[uuid.UUID, Article]:
    """One representative article per publisher.

    A publisher can reach us twice — from its own feed and again credited by an
    aggregator. The transparency panel must still show that publisher once, so
    prefer the article we fetched from the publisher directly, then the earliest.
    """
    best: dict[uuid.UUID, Article] = {}
    for article in articles:
        source = article.source
        if source is None or source.kind == SourceKind.AGGREGATOR:
            continue
        current = best.get(source.id)
        if current is None:
            best[source.id] = article
            continue
        direct_new = article.discovery_channel == "publisher_feed"
        direct_old = current.discovery_channel == "publisher_feed"
        if direct_new and not direct_old:
            best[source.id] = article
        elif direct_new == direct_old:
            new_at = article.published_at
            old_at = current.published_at
            if new_at and (old_at is None or new_at < old_at):
                best[source.id] = article
    return best


def _sync_story_sources(db: Session, story: Story) -> None:
    existing = {ss.source_id: ss for ss in story.story_sources}
    representatives = _best_article_per_source(list(story.articles))
    seen: set[uuid.UUID] = set()
    for article in representatives.values():
        source = article.source
        seen.add(source.id)
        row = existing.get(source.id)
        if row is None:
            row = StorySource(story_id=story.id, source_id=source.id)
            db.add(row)
            story.story_sources.append(row)
        row.article_id = article.id
        row.source_name = source.name
        row.source_kind = source.kind
        row.original_headline = article.headline
        row.original_url = article.canonical_url
        row.published_at = article.published_at
        row.is_primary_source = source.kind == SourceKind.OFFICIAL
    for source_id, row in existing.items():
        if source_id not in seen:
            db.delete(row)


def _refresh_story_counts(story: Story) -> None:
    sources = [ss for ss in story.story_sources]
    facets = [
        SourceFacet(
            slug=ss.source.slug,
            name=ss.source_name,
            kind=ss.source_kind,
            country=ss.source.country,
            is_independent=ss.source.is_independent,
        )
        for ss in sources
        if ss.source is not None
    ]
    diversity = compute_diversity(facets)
    story.source_count = len(sources)
    story.independent_source_count = diversity.independent
    story.diversity_level = diversity.level
    story.diversity_breakdown = {**diversity.as_dict(), "lines": describe(diversity)}
    story.has_official_source = diversity.has_official
    stamps = [a.published_at for a in story.articles if a.published_at]
    if stamps:
        story.first_reported_at = min(stamps)
        story.last_reported_at = max(stamps)


def run_clustering(db: Session, *, lookback_hours: int | None = None) -> dict:
    settings = get_settings()
    stats = StageStats("clustering")
    lookback = lookback_hours or settings.ingest_lookback_hours
    cutoff = datetime.now(UTC) - timedelta(hours=lookback)

    pending = db.scalars(
        select(Article)
        .options(selectinload(Article.source))
        .where(Article.status == ProcessingStatus.PENDING, Article.published_at >= cutoff)
        .order_by(Article.published_at.desc())
        .limit(1500)
    ).all()
    # Recently clustered articles are included so a new report can join the
    # story it belongs to instead of starting a near-duplicate one.
    recent = db.scalars(
        select(Article)
        .options(selectinload(Article.source))
        .where(
            Article.status != ProcessingStatus.PENDING,
            Article.published_at >= cutoff,
            Article.story_id.is_not(None),
        )
        .order_by(Article.published_at.desc())
        .limit(1500)
    ).all()

    stats.processed = len(pending)
    if not pending:
        return stats.as_dict()

    pool = {a.id: a for a in [*pending, *recent]}
    rows = [
        {
            "key": str(a.id),
            "headline": a.headline,
            "summary": a.feed_summary or "",
            "published_at": a.published_at,
            "source_slug": a.source.slug if a.source else "",
            "embedding": a.embedding,
        }
        for a in pool.values()
    ]
    clusters: list[Cluster] = cluster_items(build_items(rows))
    categories = db.scalars(select(Category)).all()

    for cluster in clusters:
        members = [pool[uuid.UUID(k)] for k in cluster.keys if uuid.UUID(k) in pool]
        if not members:
            continue
        if not any(m.status == ProcessingStatus.PENDING for m in members):
            continue  # nothing new in this cluster

        existing_ids = {m.story_id for m in members if m.story_id}
        story: Story | None = None
        if existing_ids:
            story = db.get(Story, next(iter(existing_ids)))
        if story is None:
            representative = cluster.representative()
            story = Story(
                headline=representative.headline,
                slug=story_slug(representative.headline, datetime.now(UTC)),
                summary="",
                summary_word_count=0,
                status=ProcessingStatus.PENDING,
            )
            db.add(story)
            db.flush()
            stats.created += 1
        else:
            stats.updated += 1
            # New reporting arrived: this story needs re-summarising.
            if story.status in (ProcessingStatus.READY, ProcessingStatus.PUBLISHED):
                story.status = ProcessingStatus.PENDING

        for member in members:
            member.story_id = story.id
            member.status = ProcessingStatus.PROCESSING
        db.flush()
        db.refresh(story)

        _sync_story_sources(db, story)
        db.flush()
        _refresh_story_counts(story)

        category = categorise(list(story.articles), categories)
        if category is not None:
            story.category_id = category.id
        story.entity_keys = sorted(cluster.entity_keys)[:40]
        story.centroid = cluster.centroid_vector

    db.flush()
    return stats.as_dict()


# ---------------------------------------------------------------------------
# Stage 3 — extraction, summarisation, ranking, quality control
# ---------------------------------------------------------------------------


def process_story(db: Session, story: Story, *, published_headlines: list[str] | None = None) -> str:
    """Extract, summarise, rank and gate one story. Returns its new status."""
    settings = get_settings()
    documents = _documents_for(story)
    if not documents:
        story.status = ProcessingStatus.FAILED
        story.qc_report = {"passed": False, "issues": [{"code": "no_documents",
                                                        "message": "story has no articles",
                                                        "severity": "blocker"}]}
        return story.status

    extraction, grounding = extract_facts(documents)

    # Whose words go on the card. With a model behind the facts, Briefly writes
    # its own summary from them. Without one it quotes a single outlet's own
    # headline and opening line, credited — see app/pipeline/wording.py for why
    # that is the honest choice rather than the lazy one.
    card_mode = settings.resolved_card_mode(extraction.provider)
    wording_document: SourceDocument | None = None
    headline_only = False
    if card_mode == "excerpt":
        wording = choose_wording(
            documents, limit=settings.summary_max_words, allow_headline_only=True
        )
        headline_only = wording.headline_only
        wording_document = next(
            (d for d in documents if d.index == wording.source_index), None
        )
        story.headline = wording.headline or story.headline
        story.dek = None
        story.summary = wording.summary
        story.summary_word_count = wording.word_count
        story.summary_kind = "excerpt"
        story.wording_source_name = wording.source_name or None
        summary_report = wording.as_dict()
    else:
        summary = build_summary(extraction, documents, limit=settings.summary_max_words)
        story.headline = extraction.headline or story.headline
        story.dek = extraction.dek or None
        story.summary = summary.text
        story.summary_word_count = summary.word_count
        story.summary_kind = "composed"
        story.wording_source_name = None
        summary_report = summary.as_dict()

    # Replace the fact set atomically — facts always describe the current cluster.
    for fact in list(story.facts):
        db.delete(fact)
    story.facts.clear()
    db.flush()

    by_index = {d.index: d for d in documents}
    slug_to_source = {
        a.source.slug: a.source for a in story.articles if a.source is not None
    }
    for fact in extraction.facts:
        doc = by_index.get(fact.source_index) if fact.source_index is not None else None
        source = slug_to_source.get(doc.source_slug) if doc else None
        db.add(
            ExtractedFact(
                story_id=story.id,
                source_id=source.id if source else None,
                slot=fact.slot,
                kind=fact.kind,
                text=fact.text,
                attributed_to=fact.attributed_to,
                evidence=fact.evidence,
                support_count=fact.support_count,
                confidence=fact.confidence,
                salience=fact.salience,
                extra=fact.extra,
            )
        )

    story.has_disputed_claims = any(f.kind == "disputed" for f in extraction.facts)
    story.confidence = (
        "confirmed"
        if any(f.kind == "confirmed" for f in extraction.facts)
        else ("disputed" if story.has_disputed_claims else "reported")
    )
    _refresh_story_counts(story)

    india_sources = sum(
        1 for ss in story.story_sources if ss.source is not None and ss.source.country == "IN"
    )
    ranking = rank_story(
        RankingInput(
            published_at=story.last_reported_at or story.first_reported_at,
            independent_source_count=story.independent_source_count,
            total_source_count=story.source_count,
            diversity_level=story.diversity_level,
            has_official_source=story.has_official_source,
            category_slug=story.category.slug if story.category else None,
            country_hits=india_sources,
            fact_count=len(extraction.facts),
            number_fact_count=sum(1 for f in extraction.facts if f.slot == "number"),
            has_disputed_claims=story.has_disputed_claims,
        )
    )
    story.rank_score = ranking.score
    story.rank_components = ranking.components

    report = check_story(
        headline=story.headline,
        summary=story.summary,
        facts=extraction.facts,
        documents=documents,
        grounding_rejected=len(grounding.rejected),
        existing_headlines=published_headlines or [],
        summary_word_limit=settings.summary_max_words,
        summary_kind=story.summary_kind,
        wording_document=wording_document,
        headline_only=headline_only,
    )
    if not any(f.kind == "confirmed" and f.slot == "what" for f in extraction.facts):
        # Not confirmed is not the same as false. A judgment reported by one
        # law reporter is still a judgment; it is shown, labelled REPORTED
        # with its single source, and never presented as CONFIRMED (the
        # confidence label above is computed from the facts, not from this).
        # Set BRIEFLY_REQUIRE_CORROBORATION=true to hold such stories instead.
        report.add(
            "no_corroborated_core_fact",
            "No core event fact is corroborated by multiple independent sources or an official source",
            "blocker" if settings.require_corroboration else "warning",
        )
    story.qc_report = {
        **report.as_dict(),
        "grounding": grounding.as_dict(),
        "summary": summary_report,
        "card_mode": card_mode,
        "extraction_provider": extraction.provider,
        "extraction_warnings": extraction.warnings,
    }

    if not report.passed:
        story.status = ProcessingStatus.FLAGGED
        story.published_at = None
    elif settings.qc_autopublish:
        story.status = ProcessingStatus.PUBLISHED
        story.published_at = story.published_at or datetime.now(UTC)
    else:
        story.status = ProcessingStatus.READY

    for article in story.articles:
        article.status = ProcessingStatus.READY

    # Belt and braces: the DB constraint refuses >30 words, so never hand it one.
    if count_words(story.summary) > settings.summary_max_words:  # pragma: no cover
        story.summary_word_count = settings.summary_max_words
        story.status = ProcessingStatus.FLAGGED
    return story.status


def run_processing(db: Session, *, limit: int | None = None) -> dict:
    stats = StageStats("processing")
    limit = limit or get_settings().process_batch_size
    stories = db.scalars(
        select(Story)
        .options(
            selectinload(Story.articles).selectinload(Article.source),
            selectinload(Story.story_sources).selectinload(StorySource.source),
            selectinload(Story.facts),
            selectinload(Story.category),
        )
        .where(Story.status.in_([ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]))
        # When there is more waiting than one run will take, take what matters:
        # the stories most outlets are reporting, then the newest. A fresh
        # database on a busy day holds a thousand clusters created in the same
        # second, and "most recently created" picks two hundred of them at
        # random.
        .order_by(
            Story.source_count.desc(),
            Story.last_reported_at.desc().nulls_last(),
            Story.created_at.desc(),
        )
        .limit(limit)
    ).all()

    published_headlines = list(
        db.scalars(
            select(Story.headline)
            .where(Story.status == ProcessingStatus.PUBLISHED)
            .order_by(Story.published_at.desc())
            .limit(300)
        ).all()
    )

    story_diagnostics = []
    for story in stories:
        stats.processed += 1
        try:
            status = process_story(db, story, published_headlines=published_headlines)
            story_diagnostics.append({
                "story_id": str(story.id),
                "headline": story.headline,
                "category": story.category.slug if story.category else None,
                "status": str(status),
                "source_count": story.source_count,
                "sources": sorted({a.source.name for a in story.articles if a.source}),
                "article_urls": [a.canonical_url or a.url for a in story.articles],
                "qc_passed": (story.qc_report or {}).get("passed"),
                "qc_issues": (story.qc_report or {}).get("issues", []),
                "confidence": story.confidence,
            })
        except Exception as exc:  # pragma: no cover - defensive
            story.status = ProcessingStatus.FAILED
            stats.errors.append(f"{story.id}: {type(exc).__name__}: {exc}")
            continue
        if status == ProcessingStatus.PUBLISHED:
            stats.published += 1
            published_headlines.append(story.headline)
        elif status == ProcessingStatus.FLAGGED:
            stats.flagged += 1
    db.flush()
    result = stats.as_dict()
    result["story_diagnostics"] = story_diagnostics[-300:]
    return result


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------


def run_full(db: Session, *, skip_ingest: bool = False) -> dict:
    run = PipelineRun(kind="full", status=ProcessingStatus.PROCESSING)
    db.add(run)
    db.flush()

    stats: dict = {}
    try:
        stats["ingest"] = {"skipped": True} if skip_ingest else run_ingest(db)
        stats["clustering"] = run_clustering(db)
        stats["processing"] = run_processing(db)
        run.status = ProcessingStatus.READY
    except Exception as exc:
        run.status = ProcessingStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        run.stats = stats
        run.finished_at = datetime.now(UTC)
        db.flush()
        raise
    run.stats = stats
    run.finished_at = datetime.now(UTC)
    db.flush()
    return stats
