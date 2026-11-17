"""Admin and pipeline control. Every route requires ``X-Admin-Token``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_admin
from app.enums import EpisodeKind, ProcessingStatus
from app.ingestion.registry import sync_categories, sync_sources
from app.models import Article, PodcastEpisode, Source, Story, StorySource
from app.pipeline import orchestrator
from app.podcast import service as podcast_service
from app.serializers import serialise_episode, serialise_story

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/seed")
def seed_reference_data(db: Session = Depends(get_db)) -> dict:
    categories = sync_categories(db)
    sources = sync_sources(db)
    db.commit()
    return {"categories": len(categories), "sources": len(sources)}


@router.post("/pipeline/ingest")
def ingest(db: Session = Depends(get_db)) -> dict:
    stats = orchestrator.run_ingest(db)
    db.commit()
    return stats


@router.post("/pipeline/cluster")
def cluster(db: Session = Depends(get_db)) -> dict:
    stats = orchestrator.run_clustering(db)
    db.commit()
    return stats


@router.post("/pipeline/process")
def process(db: Session = Depends(get_db)) -> dict:
    stats = orchestrator.run_processing(db)
    db.commit()
    return stats


@router.post("/pipeline/run")
def run_full(
    db: Session = Depends(get_db),
    skip_ingest: bool = Query(default=False),
) -> dict:
    stats = orchestrator.run_full(db, skip_ingest=skip_ingest)
    db.commit()
    return stats


@router.post("/podcast/daily")
def build_daily(
    db: Session = Depends(get_db),
    voice: bool = Query(default=True, description="Also synthesise audio"),
) -> dict:
    episode = podcast_service.generate_daily_episode(db)
    if episode is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No published stories to narrate yet.")
    if voice and episode.status != ProcessingStatus.FLAGGED:
        podcast_service.synthesise_episode(db, episode)
    db.commit()
    return {
        "episode": serialise_episode(episode, include_transcript=True).model_dump(mode="json"),
        "qc": episode.qc_report,
    }


@router.post("/podcast/deep-dive")
def build_deep_dive(
    db: Session = Depends(get_db),
    story_id: uuid.UUID | None = Query(default=None),
    voice: bool = Query(default=True),
) -> dict:
    episode = podcast_service.generate_deep_dive_episode(db, story_id=story_id)
    if episode is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No suitable story for a Deep Dive.")
    if voice and episode.status != ProcessingStatus.FLAGGED:
        podcast_service.synthesise_episode(db, episode)
    db.commit()
    return {
        "episode": serialise_episode(episode, include_transcript=True).model_dump(mode="json"),
        "qc": episode.qc_report,
    }


@router.get("/stories/flagged")
def flagged_stories(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)) -> dict:
    rows = db.scalars(
        select(Story)
        .options(
            selectinload(Story.category),
            selectinload(Story.facts),
            selectinload(Story.story_sources).selectinload(StorySource.source),
        )
        .where(Story.status == ProcessingStatus.FLAGGED)
        .order_by(Story.updated_at.desc())
        .limit(limit)
    ).all()
    return {
        "items": [
            {
                "story": serialise_story(r).model_dump(mode="json"),
                "qc_report": r.qc_report,
            }
            for r in rows
        ]
    }


@router.post("/stories/{story_id}/publish")
def publish_story(story_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Human override after reviewing a flagged story."""
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found.")
    story.status = ProcessingStatus.PUBLISHED
    story.published_at = story.published_at or datetime.now(UTC)
    story.qc_report = {**(story.qc_report or {}), "manual_override": True}
    db.commit()
    return {"id": str(story.id), "status": story.status}


@router.post("/stories/{story_id}/archive")
def archive_story(story_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found.")
    story.status = ProcessingStatus.ARCHIVED
    db.commit()
    return {"id": str(story.id), "status": story.status}


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Source).order_by(Source.name)).all()
    return {
        "items": [
            {
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind,
                "access": s.access,
                "country": s.country,
                "feed_url": s.feed_url,
                "is_enabled": s.is_enabled,
                "last_fetched_at": s.last_fetched_at,
                "last_error": s.last_error,
                "consecutive_failures": s.consecutive_failures,
            }
            for s in rows
        ]
    }


@router.post("/sources/{slug}/toggle")
def toggle_source(slug: str, enabled: bool, db: Session = Depends(get_db)) -> dict:
    source = db.scalar(select(Source).where(Source.slug == slug))
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
    source.is_enabled = enabled
    db.commit()
    return {"slug": slug, "is_enabled": source.is_enabled}


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    def count(model, **filters):
        stmt = select(model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        return len(db.scalars(stmt).all())

    return {
        "articles": count(Article),
        "stories_published": count(Story, status=ProcessingStatus.PUBLISHED),
        "stories_flagged": count(Story, status=ProcessingStatus.FLAGGED),
        "stories_pending": count(Story, status=ProcessingStatus.PENDING),
        "episodes_daily": count(PodcastEpisode, kind=EpisodeKind.DAILY),
        "episodes_deep_dive": count(PodcastEpisode, kind=EpisodeKind.DEEP_DIVE),
    }
