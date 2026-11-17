"""Optional server-side bookmark sync.

v1 of the app keeps bookmarks on the device. These endpoints exist so the same
list can follow a reader to a second device later without a schema change; the
app calls them only when sync is switched on in Settings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_client
from app.enums import ProcessingStatus
from app.models import Bookmark, Story, StorySource, User
from app.schemas import BookmarkIn, BookmarkOut, StoryOut
from app.serializers import serialise_story

router = APIRouter(prefix="/v1/bookmarks", tags=["bookmarks"],
                   dependencies=[Depends(require_client)])


def _get_or_create_user(db: Session, device_id: str) -> User:
    if len(device_id) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "device_id is too short.")
    user = db.scalar(select(User).where(User.device_id == device_id))
    if user is None:
        user = User(device_id=device_id)
        db.add(user)
        db.flush()
    user.last_seen_at = datetime.now(UTC)
    return user


@router.get("", response_model=list[StoryOut])
def list_bookmarks(
    device_id: str = Query(min_length=6, max_length=128),
    db: Session = Depends(get_db),
) -> list[StoryOut]:
    user = db.scalar(select(User).where(User.device_id == device_id))
    if user is None:
        return []
    rows = db.scalars(
        select(Story)
        .options(
            selectinload(Story.category),
            selectinload(Story.facts),
            selectinload(Story.story_sources).selectinload(StorySource.source),
        )
        .join(Bookmark, Bookmark.story_id == Story.id)
        .where(Bookmark.user_id == user.id, Story.status == ProcessingStatus.PUBLISHED)
        .order_by(Bookmark.created_at.desc())
    ).all()
    return [serialise_story(r) for r in rows]


@router.post("", response_model=BookmarkOut, status_code=status.HTTP_201_CREATED)
def create_bookmark(payload: BookmarkIn, db: Session = Depends(get_db)) -> BookmarkOut:
    user = _get_or_create_user(db, payload.device_id)
    story = db.get(Story, payload.story_id)
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found.")
    existing = db.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.story_id == story.id)
    )
    if existing is None:
        existing = Bookmark(user_id=user.id, story_id=story.id, note=payload.note)
        db.add(existing)
        db.flush()
    elif payload.note is not None:
        existing.note = payload.note
    db.commit()
    return BookmarkOut(story_id=existing.story_id, created_at=existing.created_at,
                       note=existing.note)


@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark(
    story_id: uuid.UUID,
    device_id: str = Query(min_length=6, max_length=128),
    db: Session = Depends(get_db),
) -> None:
    user = db.scalar(select(User).where(User.device_id == device_id))
    if user is None:
        return
    row = db.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.story_id == story_id)
    )
    if row is not None:
        db.delete(row)
        db.commit()
