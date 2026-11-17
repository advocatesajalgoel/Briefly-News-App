"""ORM -> API shapes."""

from __future__ import annotations

from app.models import PodcastEpisode, Story
from app.schemas import (
    DiversityOut,
    EpisodeOut,
    EpisodeSegmentOut,
    FactOut,
    SourceOut,
    StoryOut,
)

# Facts the app actually renders. The rest stay server-side.
_APP_FACT_KINDS = {"confirmed", "attributed", "disputed", "uncertain", "number", "date"}


def serialise_story(story: Story, *, include_facts: bool = True) -> StoryOut:
    breakdown = story.diversity_breakdown or {}
    diversity = DiversityOut(
        level=story.diversity_level,
        total=breakdown.get("total", story.source_count),
        independent=breakdown.get("independent", story.independent_source_count),
        countries=breakdown.get("countries", 0),
        has_official=breakdown.get("has_official", story.has_official_source),
        lines=breakdown.get("lines", []),
        by_kind=(breakdown.get("breakdown") or {}).get("by_kind", {}),
        by_country=(breakdown.get("breakdown") or {}).get("by_country", {}),
    )
    sources = [
        SourceOut(
            source_name=ss.source_name,
            source_kind=ss.source_kind,
            original_headline=ss.original_headline,
            original_url=ss.original_url,
            published_at=ss.published_at,
            is_primary_source=ss.is_primary_source,
        )
        for ss in sorted(
            story.story_sources,
            key=lambda s: (not s.is_primary_source, s.published_at or s.created_at),
        )
    ]
    first_reported_source = min(
        (row for row in story.story_sources if row.published_at is not None),
        key=lambda row: row.published_at,
        default=None,
    )
    image_article = next(
        (
            article for article in sorted(
                story.articles,
                key=lambda a: (a.discovery_channel != "publisher_feed", a.published_at or story.created_at),
            )
            if (article.raw or {}).get("image_url")
        ),
        None,
    )
    facts: list[FactOut] = []
    if include_facts:
        facts = [
            FactOut(
                slot=f.slot,
                kind=f.kind,
                text=f.text,
                attributed_to=f.attributed_to,
                support_count=f.support_count,
            )
            for f in sorted(story.facts, key=lambda f: (-f.salience, -f.support_count))
            if f.kind in _APP_FACT_KINDS
        ][:24]

    return StoryOut(
        id=story.id,
        slug=story.slug,
        headline=story.headline,
        summary=story.summary,
        summary_word_count=story.summary_word_count,
        summary_kind=story.summary_kind or "composed",
        summary_source=story.wording_source_name,
        dek=story.dek,
        image_url=(image_article.raw or {}).get("image_url") if image_article else None,
        image_source=image_article.source.name if image_article and image_article.source else None,
        category_slug=story.category.slug if story.category else None,
        category_name=story.category.name if story.category else None,
        published_at=story.published_at,
        first_reported_at=story.first_reported_at,
        first_reported_source=first_reported_source.source_name if first_reported_source else None,
        last_reported_at=story.last_reported_at,
        source_count=story.source_count,
        independent_source_count=story.independent_source_count,
        has_official_source=story.has_official_source,
        has_disputed_claims=story.has_disputed_claims,
        confidence=story.confidence,
        diversity=diversity,
        sources=sources,
        facts=facts,
        rank_score=story.rank_score,
    )


def serialise_episode(episode: PodcastEpisode, *, include_transcript: bool = False) -> EpisodeOut:
    segments = [
        EpisodeSegmentOut(
            kind=s.get("kind", "story"),
            title=s.get("title"),
            story_id=s.get("story_id"),
            word_count=s.get("word_count", 0),
            start_offset_seconds=s.get("start_offset_seconds", 0),
        )
        for s in (episode.script_segments or [])
    ]
    return EpisodeOut(
        id=episode.id,
        kind=episode.kind,
        slug=episode.slug,
        title=episode.title,
        subtitle=episode.subtitle,
        edition_date=episode.edition_date,
        published_at=episode.published_at,
        audio_url=episode.audio_url,
        audio_mime_type=episode.audio_mime_type,
        audio_duration_seconds=episode.audio_duration_seconds,
        audio_bytes=episode.audio_bytes,
        estimated_duration_seconds=episode.estimated_duration_seconds,
        script_word_count=episode.script_word_count,
        segments=segments,
        story_ids=[e.story_id for e in episode.entries],
        transcript=episode.script if include_transcript else None,
    )
