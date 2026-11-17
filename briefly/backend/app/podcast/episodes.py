"""Episode script assembly: Briefly Daily and Story Deep Dive."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.enums import EpisodeKind
from app.podcast.brief import StoryBrief
from app.podcast.narrator import (
    WORDS_PER_MINUTE,
    compose_daily_segment,
    compose_deep_dive,
    estimate_seconds,
)
from app.text.wordcount import count_words

# Target windows, in seconds, from the product spec.
DAILY_TARGET_SECONDS = (5 * 60, 10 * 60)
DEEP_DIVE_TARGET_SECONDS = (10 * 60, 20 * 60)

DAILY_MAX_STORIES = 12
DAILY_MIN_STORIES = 3


@dataclass
class Segment:
    kind: str                    # intro | story | transition | outro
    text: str
    story_id: str | None = None
    title: str | None = None
    start_offset_seconds: int = 0

    @property
    def word_count(self) -> int:
        return count_words(self.text)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": self.text,
            "story_id": self.story_id,
            "title": self.title,
            "word_count": self.word_count,
            "start_offset_seconds": self.start_offset_seconds,
        }


@dataclass
class EpisodeScript:
    kind: str
    title: str
    subtitle: str
    edition_date: datetime
    segments: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.segments if s.text)

    @property
    def word_count(self) -> int:
        return count_words(self.text)

    @property
    def estimated_seconds(self) -> int:
        return estimate_seconds(self.text)

    def story_ids(self) -> list[str]:
        return [s.story_id for s in self.segments if s.story_id]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "edition_date": self.edition_date.isoformat(),
            "word_count": self.word_count,
            "estimated_duration_seconds": self.estimated_seconds,
            "segments": [s.as_dict() for s in self.segments],
        }

    def assign_offsets(self, wpm: int = WORDS_PER_MINUTE) -> None:
        offset = 0
        for segment in self.segments:
            segment.start_offset_seconds = offset
            offset += int(round(segment.word_count / max(wpm, 1) * 60))


def _greeting(edition_date: datetime) -> str:
    hour = edition_date.hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _date_phrase(edition_date: datetime) -> str:
    day = edition_date.day
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return edition_date.strftime(f"%A, the {day}{suffix} of %B")


def build_daily_script(
    briefs: list[StoryBrief],
    edition_date: datetime,
    *,
    target_seconds: tuple[int, int] = DAILY_TARGET_SECONDS,
    max_stories: int = DAILY_MAX_STORIES,
) -> EpisodeScript:
    """Briefly Daily.

    Not a reading of the cards: each story is re-narrated from its facts, with a
    stated source count and any disagreement named out loud.
    """
    lo, hi = target_seconds
    midpoint_words = int((lo + hi) / 2 / 60 * WORDS_PER_MINUTE)
    # Reserve roughly 90 words for the intro and outro together.
    body_budget = midpoint_words - 90

    # Narrate stories until the episode reaches the target window, rather than
    # stretching a fixed number of stories to fill it.
    chosen: list[tuple[StoryBrief, str]] = []
    used_words = 0
    per_story_cap = max(90, int(body_budget / max(DAILY_MIN_STORIES, 1)))
    for brief in briefs[:max_stories]:
        remaining = body_budget - used_words
        if chosen and remaining <= 40:
            break
        text = compose_daily_segment(brief, target_words=min(per_story_cap, max(remaining, 90)))
        chosen.append((brief, text))
        used_words += count_words(text)
    briefs = [b for b, _ in chosen]

    script = EpisodeScript(
        kind=EpisodeKind.DAILY,
        title=f"Briefly Daily — {edition_date.strftime('%d %B %Y')}",
        subtitle=f"{len(briefs)} stories, with their sources named.",
        edition_date=edition_date,
    )

    sections = ", ".join(
        dict.fromkeys(b.category_name or b.category.title() for b in briefs if b.category)
    )
    intro = (
        f"{_greeting(edition_date)}. This is Briefly Daily for {_date_phrase(edition_date)}. "
        f"Here are today's most important stories"
        + (f", across {sections}. " if sections else ". ")
        + "Everything you hear is assembled from the sources named alongside it. "
        "Where reporting is contested, we say so rather than picking a side."
    )
    script.segments.append(Segment(kind="intro", text=intro, title="Introduction"))

    for index, (brief, body) in enumerate(chosen, start=1):
        label = brief.category_name or (brief.category or "").title() or "Story"
        lead = f"Story {index}. {label}."
        script.segments.append(
            Segment(
                kind="story",
                text=f"{lead} {body}",
                story_id=brief.story_id,
                title=f"{index}. {brief.headline}",
            )
        )

    outro = (
        "That's your Briefly Daily briefing. Every story in this episode is on the "
        "cards in the app, with the full list of sources and links to the original "
        "reporting. That's all for today."
    )
    script.segments.append(Segment(kind="outro", text=outro, title="Outro"))
    script.assign_offsets()
    return script


def build_deep_dive_script(
    brief: StoryBrief,
    edition_date: datetime,
    *,
    target_seconds: tuple[int, int] = DEEP_DIVE_TARGET_SECONDS,
) -> EpisodeScript:
    """One story, explained rather than argued."""
    lo, hi = target_seconds
    target_words = int((lo + hi) / 2 / 60 * WORDS_PER_MINUTE)

    script = EpisodeScript(
        kind=EpisodeKind.DEEP_DIVE,
        title=f"Deep Dive — {brief.headline}",
        subtitle=f"{brief.source_count} sources, compared.",
        edition_date=edition_date,
    )

    intro = (
        f"This is a Briefly Deep Dive for {_date_phrase(edition_date)}. "
        f"One story: {brief.headline}. "
        f"We'll go through what happened, what is actually confirmed, how the "
        f"{brief.source_count} sources we have differ, and what the reporting says comes next. "
        "This is an explanation, not an argument."
    )
    script.segments.append(Segment(kind="intro", text=intro, title="Introduction"))

    body = compose_deep_dive(brief, target_words=target_words - 140)
    script.segments.append(
        Segment(kind="story", text=body, story_id=brief.story_id, title=brief.headline)
    )

    spoken = script.estimated_seconds
    shortfall = ""
    if spoken < lo:
        # Honesty beats padding: say the material ran out rather than inventing more.
        shortfall = (
            " This episode is shorter than a usual Deep Dive because the available "
            "reporting on this story is still thin. We would rather stop than fill time."
        )

    outro = (
        "That's the Deep Dive. Every source quoted is listed on the story card in the app, "
        "with links to the original reporting, so you can check any of it yourself." + shortfall
    )
    script.segments.append(Segment(kind="outro", text=outro, title="Outro"))
    script.assign_offsets()
    return script


def select_daily_stories(briefs: list[StoryBrief], max_stories: int = DAILY_MAX_STORIES) -> list[StoryBrief]:
    """One story per section first, then the strongest remainder.

    Gives the episode the India / World / Business / Technology / Science shape
    the spec asks for, without hard-coding those five sections.
    """
    preferred_order = ["india", "world", "business", "technology", "science", "sports",
                       "entertainment"]
    by_category: dict[str, list[StoryBrief]] = {}
    for brief in briefs:
        by_category.setdefault(brief.category or "other", []).append(brief)

    picked: list[StoryBrief] = []
    used: set[str] = set()
    for slug in preferred_order:
        bucket = by_category.get(slug)
        if bucket:
            picked.append(bucket[0])
            used.add(bucket[0].story_id)
        if len(picked) >= max_stories:
            return picked

    for brief in briefs:
        if brief.story_id in used:
            continue
        picked.append(brief)
        used.add(brief.story_id)
        if len(picked) >= max_stories:
            break
    return picked


def select_deep_dive_story(briefs: list[StoryBrief], min_sources: int = 3) -> StoryBrief | None:
    """The best-covered story available — a Deep Dive needs material to compare."""
    eligible = [b for b in briefs if b.source_count >= min_sources]
    if not eligible:
        eligible = briefs
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda b: (b.source_count, len(b.facts), b.has_official_source, b.has_disputed_claims),
    )
