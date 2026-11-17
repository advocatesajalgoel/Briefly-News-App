"""Podcast endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_client
from app.enums import EpisodeKind, ProcessingStatus
from app.models import PodcastEpisode
from app.schemas import EpisodeOut, EpisodePage
from app.serializers import serialise_episode

router = APIRouter(prefix="/v1/podcast", tags=["podcast"], dependencies=[Depends(require_client)])

_LOADERS = (selectinload(PodcastEpisode.entries),)


@router.get("/episodes", response_model=EpisodePage)
def list_episodes(
    db: Session = Depends(get_db),
    kind: str | None = Query(default=None, pattern="^(daily|deep_dive)$"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> EpisodePage:
    stmt = (
        select(PodcastEpisode)
        .options(*_LOADERS)
        .where(PodcastEpisode.status == ProcessingStatus.PUBLISHED)
    )
    if kind:
        stmt = stmt.where(PodcastEpisode.kind == kind)
    stmt = stmt.order_by(PodcastEpisode.edition_date.desc()).offset(offset).limit(limit + 1)
    rows = list(db.scalars(stmt).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = str(offset + limit)
    return EpisodePage(items=[serialise_episode(r) for r in rows], next_cursor=next_cursor)


@router.get("/latest", response_model=EpisodeOut)
def latest_episode(
    db: Session = Depends(get_db),
    kind: str = Query(default=EpisodeKind.DAILY, pattern="^(daily|deep_dive)$"),
) -> EpisodeOut:
    episode = db.scalar(
        select(PodcastEpisode)
        .options(*_LOADERS)
        .where(
            PodcastEpisode.kind == kind,
            PodcastEpisode.status == ProcessingStatus.PUBLISHED,
        )
        .order_by(PodcastEpisode.edition_date.desc())
    )
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No published {kind} episode yet.")
    return serialise_episode(episode, include_transcript=True)


@router.get("/episodes/{episode_id}", response_model=EpisodeOut)
def get_episode(episode_id: uuid.UUID, db: Session = Depends(get_db)) -> EpisodeOut:
    episode = db.scalar(
        select(PodcastEpisode).options(*_LOADERS).where(PodcastEpisode.id == episode_id)
    )
    if episode is None or episode.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Episode not found.")
    return serialise_episode(episode, include_transcript=True)
