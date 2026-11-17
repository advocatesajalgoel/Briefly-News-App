"""Story ranking.

Explicitly *not* optimised for clicks. There is no engagement signal anywhere in
this function — no taps, no dwell time, no share counts. Every component is
either about how well-sourced a story is or how relevant it is to the reader's
place and section.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.enums import DiversityLevel

# Weights sum to 1.0. Kept as a module constant so a change is visible in diffs.
WEIGHTS = {
    "recency": 0.26,
    "independent_sources": 0.24,
    "diversity": 0.14,
    "primary_source": 0.12,
    "geographic": 0.10,
    "topic": 0.08,
    "substance": 0.06,
}

# Half-life of freshness, in hours.
RECENCY_HALF_LIFE_HOURS = 9.0


@dataclass
class RankingInput:
    published_at: datetime | None
    independent_source_count: int
    total_source_count: int
    diversity_level: str
    has_official_source: bool
    category_slug: str | None
    country_hits: int = 0            # how many sources are from the reader's country
    fact_count: int = 0
    number_fact_count: int = 0
    has_disputed_claims: bool = False
    now: datetime | None = None
    preferred_categories: list[str] = field(default_factory=list)


@dataclass
class RankingResult:
    score: float
    components: dict

    def as_dict(self) -> dict:
        return {"score": self.score, "components": self.components}


def recency_score(published_at: datetime | None, now: datetime | None = None) -> float:
    if published_at is None:
        return 0.3
    now = now or datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    return math.pow(0.5, hours / RECENCY_HALF_LIFE_HOURS)


def source_score(independent: int) -> float:
    """Diminishing returns: the 2nd independent source matters far more than the 9th."""
    if independent <= 0:
        return 0.0
    return min(1.0, math.log(1 + independent) / math.log(1 + 8))


def diversity_score(level: str) -> float:
    return {DiversityLevel.HIGH: 1.0, DiversityLevel.MEDIUM: 0.6, DiversityLevel.LOW: 0.25}.get(
        level, 0.25
    )


def geographic_score(country_hits: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, country_hits / total + (0.2 if country_hits else 0.0))


def topic_score(category_slug: str | None, preferred: list[str]) -> float:
    if not category_slug:
        return 0.4
    if not preferred:
        return 0.5
    return 1.0 if category_slug in preferred else 0.35


def substance_score(fact_count: int, number_facts: int) -> float:
    """Rewards stories that carry checkable specifics rather than vibes."""
    if fact_count <= 0:
        return 0.0
    base = min(1.0, fact_count / 12.0)
    specifics = min(1.0, number_facts / 4.0)
    return 0.6 * base + 0.4 * specifics


def rank_story(data: RankingInput) -> RankingResult:
    components = {
        "recency": recency_score(data.published_at, data.now),
        "independent_sources": source_score(data.independent_source_count),
        "diversity": diversity_score(data.diversity_level),
        "primary_source": 1.0 if data.has_official_source else 0.0,
        "geographic": geographic_score(data.country_hits, data.total_source_count),
        "topic": topic_score(data.category_slug, data.preferred_categories),
        "substance": substance_score(data.fact_count, data.number_fact_count),
    }
    score = sum(WEIGHTS[k] * v for k, v in components.items())

    # A single-source story is a lead, not a confirmed story. Cap it so it can
    # never outrank a well-corroborated one purely on freshness.
    if data.independent_source_count <= 1:
        score = min(score, 0.55)
    if data.has_disputed_claims:
        # Not a penalty on the story — a nudge so contested stories surface with
        # their disagreement visible rather than being buried.
        score += 0.02

    return RankingResult(score=round(min(1.0, max(0.0, score)), 6), components={
        k: round(v, 4) for k, v in components.items()
    })
