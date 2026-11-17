"""Story feed endpoints — the app's primary experience."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    decode_cursor,
    encode_cursor,
    get_db,
    require_client,
)
from app.enums import ProcessingStatus
from app.models import Article, Category, Story, StorySource
from app.schemas import CategoryOut, StoryOut, StoryPage
from app.serializers import serialise_story

router = APIRouter(prefix="/v1", tags=["stories"], dependencies=[Depends(require_client)])

_STORY_LOADERS = (
    selectinload(Story.category),
    selectinload(Story.facts),
    selectinload(Story.articles).selectinload(Article.source),
    selectinload(Story.story_sources).selectinload(StorySource.source),
)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    rows = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    ).all()
    return [CategoryOut.model_validate(r) for r in rows]


@router.get("/stories", response_model=StoryPage)
def list_stories(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None, description="Category slug; omit or use 'for-you' for the ranked mix"),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> StoryPage:
    """Ranked, cursor-paginated feed.

    'for-you' is the ranked mix across every section; any other slug filters to
    that section. Ordering is stable so the swipe stack never reshuffles under
    the reader's thumb.
    """
    stmt = (
        select(Story)
        .options(*_STORY_LOADERS)
        .where(Story.status == ProcessingStatus.PUBLISHED)
    )

    if category and category not in {"for-you", "all"}:
        cat = db.scalar(select(Category).where(Category.slug == category))
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown category '{category}'.")
        if not cat.is_synthetic:
            stmt = stmt.where(Story.category_id == cat.id)

    state = decode_cursor(cursor)
    if state:
        last_rank = float(state.get("rank", 0))
        last_id = state.get("id")
        stmt = stmt.where(
            (Story.rank_score < last_rank)
            | ((Story.rank_score == last_rank) & (Story.id > uuid.UUID(last_id)))
        )

    stmt = stmt.order_by(Story.rank_score.desc(), Story.id.asc()).limit(limit + 1)
    rows = list(db.scalars(stmt).all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = encode_cursor({"rank": tail.rank_score, "id": str(tail.id)})

    total = db.scalar(
        select(func.count(Story.id)).where(Story.status == ProcessingStatus.PUBLISHED)
    )
    return StoryPage(
        items=[serialise_story(r) for r in rows],
        next_cursor=next_cursor,
        total_estimate=total,
    )


@router.get("/stories/{story_id}", response_model=StoryOut)
def get_story(story_id: uuid.UUID, db: Session = Depends(get_db)) -> StoryOut:
    story = db.scalar(select(Story).options(*_STORY_LOADERS).where(Story.id == story_id))
    if story is None or story.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found.")
    return serialise_story(story)


@router.get("/stories/by-slug/{slug}", response_model=StoryOut)
def get_story_by_slug(slug: str, db: Session = Depends(get_db)) -> StoryOut:
    story = db.scalar(select(Story).options(*_STORY_LOADERS).where(Story.slug == slug))
    if story is None or story.status != ProcessingStatus.PUBLISHED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found.")
    return serialise_story(story)


@router.post("/stories/batch", response_model=list[StoryOut])
def get_stories_batch(ids: list[uuid.UUID], db: Session = Depends(get_db)) -> list[StoryOut]:
    """Rehydrate locally-saved bookmarks in one round trip."""
    if not ids:
        return []
    rows = db.scalars(
        select(Story)
        .options(*_STORY_LOADERS)
        .where(Story.id.in_(ids[:100]), Story.status == ProcessingStatus.PUBLISHED)
    ).all()
    order = {sid: i for i, sid in enumerate(ids)}
    return [serialise_story(r) for r in sorted(rows, key=lambda s: order.get(s.id, 999))]
