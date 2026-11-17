from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_db
from app.config import Settings, get_settings
from app.enums import ProcessingStatus
from app.models import PodcastEpisode, Story
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
@router.get("/v1/health", response_model=HealthOut)
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> HealthOut:
    database = "ok"
    published = 0
    latest_story = None
    latest_episode = None
    try:
        db.execute(text("SELECT 1"))
        published = db.scalar(
            select(func.count(Story.id)).where(Story.status == ProcessingStatus.PUBLISHED)
        ) or 0
        latest_story = db.scalar(select(func.max(Story.published_at)))
        latest_episode = db.scalar(select(func.max(PodcastEpisode.published_at)))
    except Exception as exc:  # pragma: no cover - only when the DB is down
        database = f"error: {type(exc).__name__}"

    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=__version__,
        environment=settings.env,
        database=database,
        llm_provider=settings.llm_provider,
        tts_provider=settings.tts_provider,
        storage_backend=settings.storage_backend,
        scheduler_enabled=settings.scheduler_enabled,
        published_stories=published,
        latest_story_at=latest_story,
        latest_episode_at=latest_episode,
    )
