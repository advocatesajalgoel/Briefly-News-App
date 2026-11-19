"""Podcast persistence: briefs from the DB, scripts, quality control, audio."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.enums import ProcessingStatus
from app.llm.factory import get_extraction_provider
from app.llm.schema import SourceDocument
from app.models import Article, PodcastEpisode, PodcastStory, Story, StorySource
from app.pipeline.qc import check_script
from app.podcast.brief import FactRef, SourceRef, StoryBrief
from app.podcast.episodes import (
    DAILY_TARGET_SECONDS,
    DEEP_DIVE_TARGET_SECONDS,
    EpisodeScript,
    build_daily_script,
    build_deep_dive_script,
    select_daily_stories,
    select_deep_dive_story,
)
from app.podcast.narrator import estimate_seconds
from app.storage.factory import get_storage
from app.text.wordcount import count_words
from app.tts.base import SynthesisRequest
from app.tts.factory import get_tts_provider

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str, max_len: int = 90) -> str:
    return _SLUG_RE.sub("-", (value or "").lower()).strip("-")[:max_len] or "episode"


# ---------------------------------------------------------------------------
# Briefs
# ---------------------------------------------------------------------------


def build_story_brief(story: Story) -> StoryBrief:
    return StoryBrief(
        story_id=str(story.id),
        headline=story.headline,
        summary=story.summary,
        dek=story.dek or "",
        category=story.category.slug if story.category else "",
        category_name=story.category.name if story.category else "",
        published_at=story.published_at or story.last_reported_at,
        source_count=story.source_count,
        independent_source_count=story.independent_source_count,
        has_official_source=story.has_official_source,
        has_disputed_claims=story.has_disputed_claims,
        diversity_level=story.diversity_level,
        diversity_lines=list((story.diversity_breakdown or {}).get("lines", [])),
        sources=[
            SourceRef(
                name=ss.source_name,
                kind=ss.source_kind,
                headline=ss.original_headline,
                url=ss.original_url,
                published_at=ss.published_at,
                is_primary=ss.is_primary_source,
            )
            for ss in sorted(story.story_sources, key=lambda s: (not s.is_primary_source,
                                                                s.source_name))
        ],
        facts=[
            FactRef(
                slot=f.slot,
                kind=f.kind,
                text=f.text,
                attributed_to=f.attributed_to,
                support_count=f.support_count,
            )
            for f in sorted(story.facts, key=lambda f: (-f.salience, -f.support_count))
        ],
    )


def _documents_for_story(story: Story) -> list[SourceDocument]:
    return [
        SourceDocument(
            index=i,
            source_slug=a.source.slug if a.source else "",
            source_name=a.source.name if a.source else "",
            source_kind=a.source.kind if a.source else "other",
            headline=a.headline,
            summary=a.feed_summary or "",
            url=a.canonical_url,
        )
        for i, a in enumerate(story.articles)
    ]


def _published_stories(db: Session, *, since_hours: int = 30, limit: int = 60) -> list[Story]:
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    return list(
        db.scalars(
            select(Story)
            .options(
                selectinload(Story.category),
                selectinload(Story.facts),
                selectinload(Story.story_sources).selectinload(StorySource.source),
                selectinload(Story.articles).selectinload(Article.source),
            )
            .where(
                Story.status == ProcessingStatus.PUBLISHED,
                Story.published_at.is_not(None),
                Story.published_at >= cutoff,
                # A judgment the Arbitration desk keeps for a week is shown on
                # its card as days old; a daily briefing must not voice it as
                # today's news.
                or_(
                    Story.last_reported_at.is_(None),
                    Story.last_reported_at
                    >= datetime.now(UTC) - timedelta(hours=get_settings().ingest_lookback_hours),
                ),
            )
            .order_by(Story.rank_score.desc(), Story.published_at.desc())
            .limit(limit)
        ).all()
    )


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------


def _use_hosted_narrator(script: EpisodeScript, briefs_by_id: dict[str, StoryBrief],
                         mode: str) -> EpisodeScript:
    """Let a configured model rewrite each story segment from the same facts."""
    provider = get_extraction_provider()
    if provider.name == "rule_based":
        return script  # already the rule-based narration
    for segment in script.segments:
        if segment.kind != "story" or not segment.story_id:
            continue
        brief = briefs_by_id.get(segment.story_id)
        if brief is None:
            continue
        target = max(60, count_words(segment.text))
        try:
            rewritten = provider.write_narration(brief.as_dict(), target, mode)
        except Exception:
            continue
        if rewritten and count_words(rewritten) >= 25:
            head = segment.text.split(".", 1)[0]
            segment.text = f"{head}. {rewritten.strip()}"
    script.assign_offsets()
    return script


def _persist_script(
    db: Session,
    script: EpisodeScript,
    briefs_by_id: dict[str, StoryBrief],
    qc: dict,
    status: str,
) -> PodcastEpisode:
    slug = f"{script.kind}-{script.edition_date:%Y%m%d}-{_slug(script.title)[:40]}"
    existing = db.scalar(select(PodcastEpisode).where(PodcastEpisode.slug == slug))
    episode = existing or PodcastEpisode(slug=slug)
    if existing is None:
        db.add(episode)

    episode.kind = script.kind
    episode.title = script.title
    episode.subtitle = script.subtitle
    episode.edition_date = script.edition_date
    episode.script = script.text
    episode.script_segments = [s.as_dict() for s in script.segments]
    episode.script_word_count = script.word_count
    episode.estimated_duration_seconds = script.estimated_seconds
    episode.qc_report = qc
    episode.status = status
    db.flush()

    for entry in list(episode.entries):
        db.delete(entry)
    episode.entries.clear()
    db.flush()

    position = 0
    for segment in script.segments:
        if segment.kind != "story" or not segment.story_id:
            continue
        entry = PodcastStory(
            episode_id=episode.id,
            story_id=uuid.UUID(segment.story_id),
            position=position,
            segment_title=segment.title,
            narration=segment.text,
            word_count=segment.word_count,
            start_offset_seconds=segment.start_offset_seconds,
        )
        db.add(entry)
        # Attach to the loaded relationship as well, so a caller holding this
        # episode sees its entries without a refresh round trip.
        episode.entries.append(entry)
        position += 1
    db.flush()
    return episode


def _qc_for(script: EpisodeScript, stories: list[Story],
            target: tuple[int, int]) -> dict:
    documents: list[SourceDocument] = []
    for story in stories:
        documents.extend(_documents_for_story(story))
    # The framing the show itself supplies is not a publisher's words, so it is
    # excluded from the copying and grounding checks.
    story_text = "\n\n".join(s.text for s in script.segments if s.kind == "story")
    # Counts Briefly derives from its own data are legitimate for the narrator to
    # state even though no publisher wrote them down.
    allowed_numbers = {str(i) for i in range(1, len(stories) + 2)}
    for story in stories:
        allowed_numbers.add(str(story.source_count))
        allowed_numbers.add(str(story.independent_source_count))
    report = check_script(
        script=story_text,
        documents=documents,
        target_seconds=target,
        allowed_numbers=allowed_numbers,
    )
    return report.as_dict()


def generate_daily_episode(
    db: Session,
    edition_date: datetime | None = None,
    *,
    max_stories: int | None = None,
) -> PodcastEpisode | None:
    settings = get_settings()
    edition_date = edition_date or datetime.now(UTC)
    stories = _published_stories(db)
    if not stories:
        return None

    briefs = [build_story_brief(s) for s in stories]
    selected = select_daily_stories(briefs, max_stories=max_stories or 12)
    script = build_daily_script(selected, edition_date)
    briefs_by_id = {b.story_id: b for b in briefs}
    script = _use_hosted_narrator(script, briefs_by_id, "daily")

    used_ids = {uuid.UUID(i) for i in script.story_ids()}
    used_stories = [s for s in stories if s.id in used_ids]
    qc = _qc_for(script, used_stories, DAILY_TARGET_SECONDS)

    status = (
        ProcessingStatus.READY
        if qc["passed"] and settings.qc_autopublish
        else (ProcessingStatus.FLAGGED if not qc["passed"] else ProcessingStatus.READY)
    )
    return _persist_script(db, script, briefs_by_id, qc, status)


def generate_deep_dive_episode(
    db: Session,
    story_id: uuid.UUID | None = None,
    edition_date: datetime | None = None,
) -> PodcastEpisode | None:
    edition_date = edition_date or datetime.now(UTC)
    if story_id is not None:
        story = db.get(Story, story_id)
        stories = [story] if story else []
    else:
        stories = _published_stories(db)
    if not stories:
        return None

    briefs = [build_story_brief(s) for s in stories]
    brief = briefs[0] if story_id is not None else select_deep_dive_story(briefs)
    if brief is None:
        return None

    script = build_deep_dive_script(brief, edition_date)
    briefs_by_id = {brief.story_id: brief}
    script = _use_hosted_narrator(script, briefs_by_id, "deep_dive")

    target_story = next((s for s in stories if str(s.id) == brief.story_id), stories[0])
    qc = _qc_for(script, [target_story], DEEP_DIVE_TARGET_SECONDS)
    status = ProcessingStatus.FLAGGED if not qc["passed"] else ProcessingStatus.READY
    return _persist_script(db, script, briefs_by_id, qc, status)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


def synthesise_episode(db: Session, episode: PodcastEpisode, *, publish: bool = True) -> PodcastEpisode:
    settings = get_settings()
    if episode.status == ProcessingStatus.FLAGGED:
        raise ValueError(
            "episode failed quality control and will not be voiced; "
            "review podcast_episodes.qc_report"
        )

    provider = get_tts_provider()
    storage = get_storage()
    result = provider.synthesise(
        SynthesisRequest(
            text=episode.script,
            voice=settings.tts_voice,
            fmt=settings.tts_format,
        )
    )
    key = f"episodes/{episode.edition_date:%Y/%m}/{episode.slug}.{result.fmt}"
    stored = storage.put(key, result.audio, result.mime_type)

    episode.audio_url = stored.url
    episode.audio_bytes = stored.size_bytes
    episode.audio_mime_type = result.mime_type
    episode.audio_duration_seconds = result.duration_seconds
    episode.tts_provider = result.provider
    episode.tts_voice = result.voice
    if result.warnings:
        episode.qc_report = {**(episode.qc_report or {}), "tts_warnings": result.warnings}

    # Re-time the chapter offsets against the audio we actually produced.
    if episode.script_word_count and result.duration_seconds:
        ratio = result.duration_seconds / max(episode.script_word_count, 1)
        running = 0
        segments = []
        for segment in episode.script_segments or []:
            segment = {**segment, "start_offset_seconds": int(running * ratio)}
            running += segment.get("word_count", 0)
            segments.append(segment)
        episode.script_segments = segments
        for entry in episode.entries:
            match = next(
                (s for s in segments if s.get("story_id") == str(entry.story_id)), None
            )
            if match:
                entry.start_offset_seconds = match["start_offset_seconds"]

    if publish:
        episode.status = ProcessingStatus.PUBLISHED
        episode.published_at = episode.published_at or datetime.now(UTC)
    db.flush()
    return episode


def build_and_voice_daily(db: Session, edition_date: datetime | None = None) -> PodcastEpisode | None:
    episode = generate_daily_episode(db, edition_date)
    if episode is None:
        return None
    if episode.status == ProcessingStatus.FLAGGED:
        return episode
    return synthesise_episode(db, episode)


def estimated_seconds_for(text: str) -> int:
    return estimate_seconds(text)
