"""Pydantic response models — the contract the iOS app codes against.

Field names here are mirrored exactly by the Swift `Codable` structs in
``ios/Briefly/Models``. Changing one means changing the other.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    sort_order: int = 100
    is_synthetic: bool = False


class SourceOut(BaseModel):
    """One row of the transparency panel."""

    model_config = ConfigDict(from_attributes=True)

    source_name: str
    source_kind: str
    original_headline: str
    original_url: str
    published_at: datetime | None = None
    is_primary_source: bool = False


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot: str
    kind: str
    text: str
    attributed_to: str | None = None
    support_count: int = 1


class DiversityOut(BaseModel):
    level: str = "low"
    total: int = 0
    independent: int = 0
    countries: int = 0
    has_official: bool = False
    lines: list[str] = Field(default_factory=list)
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_country: dict[str, int] = Field(default_factory=dict)
    # Shown verbatim in the app so the indicator is never mistaken for a bias score.
    disclaimer: str = (
        "Source diversity counts where reporting came from. It is not a measurement "
        "of bias."
    )


class StoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    headline: str
    summary: str
    summary_word_count: int
    # "excerpt": the summary is one outlet's own words, quoted and credited in
    # `summary_source`. "composed": Briefly wrote it from extracted facts.
    summary_kind: str = "composed"
    summary_source: str | None = None
    dek: str | None = None
    image_url: str | None = None
    image_source: str | None = None
    category_slug: str | None = None
    category_name: str | None = None
    published_at: datetime | None = None
    first_reported_at: datetime | None = None
    last_reported_at: datetime | None = None
    source_count: int = 0
    independent_source_count: int = 0
    has_official_source: bool = False
    has_disputed_claims: bool = False
    confidence: str = "reported"
    diversity: DiversityOut = Field(default_factory=DiversityOut)
    sources: list[SourceOut] = Field(default_factory=list)
    facts: list[FactOut] = Field(default_factory=list)
    rank_score: float = 0.0


class StoryPage(BaseModel):
    items: list[StoryOut]
    next_cursor: str | None = None
    total_estimate: int | None = None


class EpisodeSegmentOut(BaseModel):
    kind: str
    title: str | None = None
    story_id: str | None = None
    word_count: int = 0
    start_offset_seconds: int = 0


class EpisodeOut(BaseModel):
    id: uuid.UUID
    kind: str
    slug: str
    title: str
    subtitle: str | None = None
    edition_date: datetime
    published_at: datetime | None = None
    audio_url: str | None = None
    audio_mime_type: str | None = None
    audio_duration_seconds: int | None = None
    audio_bytes: int | None = None
    estimated_duration_seconds: int = 0
    script_word_count: int = 0
    segments: list[EpisodeSegmentOut] = Field(default_factory=list)
    story_ids: list[uuid.UUID] = Field(default_factory=list)
    # Full narration, so the app can show a transcript alongside the audio.
    transcript: str | None = None


class EpisodePage(BaseModel):
    items: list[EpisodeOut]
    next_cursor: str | None = None


class BookmarkIn(BaseModel):
    device_id: str = Field(min_length=6, max_length=128)
    story_id: uuid.UUID
    note: str | None = None


class BookmarkOut(BaseModel):
    story_id: uuid.UUID
    created_at: datetime
    note: str | None = None


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    llm_provider: str
    tts_provider: str
    storage_backend: str
    scheduler_enabled: bool
    published_stories: int = 0
    latest_story_at: datetime | None = None
    latest_episode_at: datetime | None = None


class PipelineRunOut(BaseModel):
    kind: str
    status: str
    stats: dict = Field(default_factory=dict)
    error: str | None = None
